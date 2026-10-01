"""
تحضير dataset من ترجمات TED المستخرجة.
- يقرأ ملفات .json من data/downloads/
- يبني أزواج (source, target)
- يفلتر الضعيف
- يقسم train/val/test
- يحفظ HuggingFace Dataset
"""
import json
import random
import logging
from pathlib import Path
from typing import List, Dict, Tuple

from datasets import Dataset, DatasetDict

logger = logging.getLogger(__name__)

DATA_DIR = Path("data/downloads")
OUT_DIR = Path("finetune/data")
OUT_DIR.mkdir(parents=True, exist_ok=True)

MIN_LEN = 10
MAX_LEN = 512
MIN_RATIO = 0.3   # نسبة طول الترجمة/الأصل


def is_valid_pair(src: str, tgt: str) -> bool:
    if not src or not tgt:
        return False
    if len(src) < MIN_LEN or len(tgt) < MIN_LEN:
        return False
    if len(src) > MAX_LEN * 4 or len(tgt) > MAX_LEN * 4:
        return False
    ratio = len(tgt) / max(len(src), 1)
    if ratio < MIN_RATIO or ratio > 1 / MIN_RATIO:
        return False
    return True


def load_pairs() -> List[Dict]:
    """تحميل أزواج من كل الملفات."""
    pairs = []
    for f in DATA_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("فشل قراءة %s: %s", f, e)
            continue

        src = data.get("source_text", "").strip()
        tgt = data.get("target_text", "").strip()
        if not src or not tgt:
            continue

        # تقسيم إلى جمل
        src_sents = [s.strip() for s in src.split(". ") if s.strip()]
        tgt_sents = [s.strip() for s in tgt.split(". ") if s.strip()]

        # موازنة تقريبية: نأخذ min length
        n = min(len(src_sents), len(tgt_sents))
        for i in range(n):
            s, t = src_sents[i], tgt_sents[i]
            if is_valid_pair(s, t):
                pairs.append({
                    "source": s,
                    "target": t,
                    "source_lang": data.get("source_lang", "en"),
                    "target_lang": data.get("target_lang", "ar"),
                    "talk_id": data.get("talk_id", ""),
                })

    logger.info("حُمِّل %d زوجًا صالحًا", len(pairs))
    return pairs


def split_data(pairs: List[Dict], seed: int = 42) -> Tuple:
    random.seed(seed)
    random.shuffle(pairs)
    n = len(pairs)
    train_end = int(n * 0.9)
    val_end = int(n * 0.95)
    return pairs[:train_end], pairs[train_end:val_end], pairs[val_end:]


def build_dataset(pairs: List[Dict]) -> DatasetDict:
    train, val, test = split_data(pairs)
    return DatasetDict({
        "train": Dataset.from_list(train),
        "validation": Dataset.from_list(val),
        "test": Dataset.from_list(test),
    })


def main():
    logging.basicConfig(level=logging.INFO)
    pairs = load_pairs()
    if len(pairs) < 100:
        logger.error("بيانات غير كافية (تحتاج 100 زوج على الأقل)")
        return

    ds = build_dataset(pairs)
    ds.save_to_disk(str(OUT_DIR / "ted_ar_en"))
    print("✅ تم حفظ Dataset:")
    print(ds)


if __name__ == "__main__":
    main()
