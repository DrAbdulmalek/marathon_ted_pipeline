"""
نظام A/B Testing لمقارنة محركات الترجمة والنماذج.

الميزات:
- تسجيل التجارب (experiments)
- توزيع عشوائي موزون على المتغيرات (variants)
- تسجيل النتائج والمقاييس
- حساب الأهمية الإحصائية (p-value)
- اختيار تلقائي للفائز
"""
import os
import json
import random
import sqlite3
import hashlib
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Tuple

logger = logging.getLogger(__name__)

DB_PATH = Path(os.getenv("AB_DB", "data/ab_testing.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


# ---------- قاعدة البيانات ----------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS experiments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            variants TEXT NOT NULL,      -- JSON: [{"name":"a","weight":50},...]
            metric TEXT NOT NULL,         -- bleu|chrf|user_rating|latency
            status TEXT DEFAULT 'active', -- active|paused|completed
            winner TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_id INTEGER NOT NULL,
            unit_id TEXT NOT NULL,        -- معرّف الوحدة (نص، مستخدم، إلخ)
            variant TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(experiment_id) REFERENCES experiments(id)
        );
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_id INTEGER NOT NULL,
            variant TEXT NOT NULL,
            unit_id TEXT NOT NULL,
            metric_value REAL NOT NULL,
            metadata TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(experiment_id) REFERENCES experiments(id)
        );
        CREATE INDEX IF NOT EXISTS idx_assign_exp
            ON assignments(experiment_id, unit_id);
        CREATE INDEX IF NOT EXISTS idx_results_exp
            ON results(experiment_id, variant);
    """)
    conn.commit()
    conn.close()


# ---------- إدارة التجارب ----------
def create_experiment(name: str, description: str,
                       variants: List[Dict], metric: str) -> int:
    """
    variants: [{"name": "google", "weight": 50}, {"name": "deepl", "weight": 50}]
    metric: bleu|chrf|meteor|user_rating|latency
    """
    # تحقق من الأوزان
    total = sum(v.get("weight", 1) for v in variants)
    if total == 0:
        raise ValueError("المجموع يجب أن يكون > 0")

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.execute(
            """INSERT INTO experiments
               (name, description, variants, metric)
               VALUES (?, ?, ?, ?)""",
            (name, description, json.dumps(variants), metric),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_experiment(name: str) -> Optional[Dict]:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            """SELECT id, name, description, variants, metric, status, winner
               FROM experiments WHERE name = ?""",
            (name,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {
        "id": row[0], "name": row[1], "description": row[2],
        "variants": json.loads(row[3]), "metric": row[4],
        "status": row[5], "winner": row[6],
    }


def list_experiments() -> List[Dict]:
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            """SELECT id, name, metric, status, winner, created_at
               FROM experiments ORDER BY created_at DESC"""
        ).fetchall()
    finally:
        conn.close()
    return [
        {"id": r[0], "name": r[1], "metric": r[2],
         "status": r[3], "winner": r[4], "created_at": r[5]}
        for r in rows
    ]


def pause_experiment(name: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.execute(
            "UPDATE experiments SET status='paused' WHERE name = ?", (name,)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def complete_experiment(name: str, winner: Optional[str] = None):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "UPDATE experiments SET status='completed', winner=? WHERE name = ?",
            (winner, name),
        )
        conn.commit()
    finally:
        conn.close()


# ---------- التخصيص (Assignment) ----------
def _hash_unit(unit_id: str, experiment_id: int) -> float:
    """توليد رقم 0-1 ثابت للوحدة (deterministic)."""
    h = hashlib.sha256(f"{experiment_id}:{unit_id}".encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def assign_variant(experiment_name: str, unit_id: str,
                    cache: bool = True) -> Optional[str]:
    """
    تخصيص variant لوحدة (نص/مستخدم).
    deterministic: نفس unit_id → نفس variant.
    """
    exp = get_experiment(experiment_name)
    if not exp or exp["status"] != "active":
        return None

    # تحقق من cache
    conn = sqlite3.connect(DB_PATH)
    try:
        if cache:
            row = conn.execute(
                """SELECT variant FROM assignments
                   WHERE experiment_id = ? AND unit_id = ?""",
                (exp["id"], unit_id),
            ).fetchone()
            if row:
                return row[0]

        # توزيع موزون
        variants = exp["variants"]
        total_weight = sum(v.get("weight", 1) for v in variants)
        target = _hash_unit(unit_id, exp["id"]) * total_weight

        cumulative = 0
        selected = variants[-1]["name"]  # افتراضي
        for v in variants:
            cumulative += v.get("weight", 1)
            if target < cumulative:
                selected = v["name"]
                break

        # سجّل التخصيص
        conn.execute(
            """INSERT INTO assignments (experiment_id, unit_id, variant)
               VALUES (?, ?, ?)""",
            (exp["id"], unit_id, selected),
        )
        conn.commit()
        return selected
    finally:
        conn.close()


# ---------- النتائج ----------
def record_result(experiment_name: str, unit_id: str,
                    metric_value: float, metadata: Dict = None) -> bool:
    exp = get_experiment(experiment_name)
    if not exp:
        return False

    # احصل على الـ variant المُخصَّص
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            """SELECT variant FROM assignments
               WHERE experiment_id = ? AND unit_id = ?""",
            (exp["id"], unit_id),
        ).fetchone()
        if not row:
            logger.warning("لا يوجد تخصيص لـ %s/%s", experiment_name, unit_id)
            return False

        variant = row[0]
        conn.execute(
            """INSERT INTO results
               (experiment_id, variant, unit_id, metric_value, metadata)
               VALUES (?, ?, ?, ?, ?)""",
            (exp["id"], variant, unit_id, metric_value,
             json.dumps(metadata or {})),
        )
        conn.commit()
        return True
    finally:
        conn.close()


# ---------- التحليل الإحصائي ----------
def _mean_std(values: List[float]) -> Tuple[float, float]:
    if not values:
        return 0.0, 0.0
    n = len(values)
    mean = sum(values) / n
    if n < 2:
        return mean, 0.0
    var = sum((x - mean) ** 2 for x in values) / (n - 1)
    return mean, math.sqrt(var)


def _t_test(a: List[float], b: List[float]) -> Tuple[float, float]:
    """
    Welch's t-test (لا يفترض تجانس التباين).
    يعيد (t_stat, approximate_p_value).
    """
    if len(a) < 2 or len(b) < 2:
        return 0.0, 1.0

    ma, sa = _mean_std(a)
    mb, sb = _mean_std(b)

    se = math.sqrt(sa ** 2 / len(a) + sb ** 2 / len(b))
    if se == 0:
        return 0.0, 1.0

    t = (ma - mb) / se

    # p-value تقريبية عبر التوزيع الطبيعي
    # (كافٍ لـ n > 30؛ للدقة استخدم scipy.stats)
    try:
        from scipy.stats import t as t_dist
        df_num = (sa ** 2 / len(a) + sb ** 2 / len(b)) ** 2
        df_den = (
            (sa ** 2 / len(a)) ** 2 / (len(a) - 1)
            + (sb ** 2 / len(b)) ** 2 / (len(b) - 1)
        )
        df = df_num / df_den if df_den else len(a) + len(b) - 2
        p = 2 * (1 - t_dist.cdf(abs(t), df))
        return t, p
    except ImportError:
        # تقريب: p ≈ exp(-|t|)
        p = math.exp(-abs(t))
        return t, min(1.0, p * 2)


def analyze_experiment(name: str) -> Dict:
    """
    تحليل تجربة: متوسطات، انحرافات، t-test، الفائز.
    """
    exp = get_experiment(name)
    if not exp:
        return {"error": "التجربة غير موجودة"}

    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            """SELECT variant, metric_value FROM results
               WHERE experiment_id = ?""",
            (exp["id"],),
        ).fetchall()
    finally:
        conn.close()

    by_variant: Dict[str, List[float]] = {}
    for variant, val in rows:
        by_variant.setdefault(variant, []).append(val)

    summary = {}
    for v, vals in by_variant.items():
        mean, std = _mean_std(vals)
        summary[v] = {
            "n": len(vals),
            "mean": round(mean, 4),
            "std": round(std, 4),
            "ci_95": (
                round(mean - 1.96 * std / math.sqrt(len(vals)), 4),
                round(mean + 1.96 * std / math.sqrt(len(vals)), 4),
            ) if len(vals) > 1 else None,
        }

    # t-test مقابل الفائز
    winner = max(summary.items(), key=lambda x: x[1]["mean"])[0] \
        if summary else None

    pairwise = {}
    variants = list(summary.keys())
    for i in range(len(variants)):
        for j in range(i + 1, len(variants)):
            va, vb = variants[i], variants[j]
            t, p = _t_test(by_variant[va], by_variant[vb])
            pairwise[f"{va}_vs_{vb}"] = {
                "t_stat": round(t, 3),
                "p_value": round(p, 4),
                "significant": p < 0.05,
                "winner": va if t > 0 else vb,
            }

    return {
        "experiment": name,
        "metric": exp["metric"],
        "status": exp["status"],
        "variants": summary,
        "winner": winner,
        "pairwise": pairwise,
        "total_results": len(rows),
    }


def auto_select_winner(name: str, min_samples: int = 100,
                        p_threshold: float = 0.05) -> Optional[str]:
    """
    اختيار فائز تلقائيًا إذا:
    - كل variant لديه min_samples
    - يوجد فرق ذو دلالة إحصائية
    """
    analysis = analyze_experiment(name)
    if "error" in analysis:
        return None

    variants = analysis["variants"]
    if not variants:
        return None

    # تحقق من عدد العينات
    for v, stats in variants.items():
        if stats["n"] < min_samples:
            logger.info("Variant %s لديه %d < %d عينة",
                        v, stats["n"], min_samples)
            return None

    # اختر الفائز
    winner = max(variants.items(), key=lambda x: x[1]["mean"])[0]

    # اختبر دلالته
    for pair, info in analysis["pairwise"].items():
        if winner in pair and info["winner"] == winner:
            if info["significant"]:
                logger.info("✅ فائز: %s (p=%.4f)",
                            winner, info["p_value"])
                complete_experiment(name, winner)
                return winner

    return None


# ---------- التكامل مع Translator ----------
def translate_with_ab(text: str, experiment_name: str,
                       unit_id: Optional[str] = None,
                       src: str = "auto", tgt: str = "ar"):
    """
    ترجمة مع A/B testing.
    unit_id يُستخدم لتوزيع ثابت — إذا None، يُولَّد من hash النص.
    """
    if unit_id is None:
        unit_id = hashlib.md5(text.encode()).hexdigest()[:16]

    variant = assign_variant(experiment_name, unit_id)
    if not variant:
        # لا تجربة نشطة — استخدم الافتراضي
        from .translator import Translator
        t = Translator(engine="google")
        result = t.translate(text, src, tgt)
        return result, None

    # variant هو اسم المحرك (google, deepl, hf)
    from .translator import Translator
    t = Translator(engine=variant)
    result = t.translate(text, src, tgt)
    return result, variant


def score_translation(experiment_name: str, unit_id: str,
                       prediction: str, reference: str,
                       source: Optional[str] = None):
    """قياس الجودة وتسجيلها في التجربة."""
    from .quality.metrics import QualityEvaluator

    evaluator = QualityEvaluator()
    score = evaluator.evaluate(
        [prediction], [reference],
        [source] if source else None,
    )

    exp = get_experiment(experiment_name)
    if not exp:
        return score

    metric_name = exp["metric"]
    value = getattr(score, metric_name, None)
    if value is None:
        value = score.overall or 0

    record_result(experiment_name, unit_id, value, {
        "prediction": prediction[:100],
        "reference": reference[:100],
    })
    return score


init_db()
