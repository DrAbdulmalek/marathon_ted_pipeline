# tests/test_ci_config.py
"""حواجز انحدار على إعداد CI نفسه (تدقيق 2026-10-03).

السبب: كل إصلاح في `.github/workflows/ci.yml` كان «إعداداً»، والإعداد يُنسخ
ويُلصق ويُعدَّل بلا اختبار، فيرجع العطل بعد أسبوع دون أن يلاحظه أحد. هذه
الاختبارات تقرأ ملف الـ workflow كنص وتفشل عند عودة أي نمط معطوب.

ما تُثبته (كل بند مبني على قياس لا على تقدير):
  1. ruff في CI مقيَّد بـ E9,F63,F7,F82 — لأن `ruff check src/ tests/` بلا
     `--select` يعطي **361 خطأ** على ruff 0.16.10 (و0 على المجموعة الحرجة)،
     فكانت أول CI حقيقية ستحمرّ فوراً عند الخطوة الأولى.
  2. أدوات الفحص مثبّتة الإصدار (ruff/mypy) — لأن ruff غيّر مجموعة قواعده
     الافتراضية بين الإصدارات.
  3. لا `|| true` على mypy — كان أخضر كاذباً يخفي 25 خطأ أنواع. البديل
     «ratchet» (ratchet) يفشل عند الزيادة فقط، وخط أساسه مُودَع في المستودع.
  4. خط أساس mypy موجود ورقمه عدد صحيح غير سالب.
  5. `branches: [main, develop]` كاملة (لا مقطوعة).
  6. لا توكن في query string بأي workflow.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
CI = WORKFLOWS / "ci.yml"
BASELINE = ROOT / ".github" / "mypy-baseline.txt"


@pytest.fixture(scope="module")
def ci_text() -> str:
    assert CI.exists(), f"missing workflow: {CI}"
    return CI.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def ci_yaml(ci_text):
    return yaml.safe_load(ci_text)


# ---------------------------------------------------------------------------
# 1) ruff مقيَّد بالمجموعة الحرجة
# ---------------------------------------------------------------------------

def test_ruff_blocking_step_is_scoped_to_critical_rules(ci_text):
    """`ruff check src/ tests/` بلا --select = 361 خطأ = CI حمراء من أول خطوة."""
    blocking = re.findall(r"run:\s*ruff check[^\n]*", ci_text)
    assert blocking, "لا توجد خطوة ruff إطلاقاً"
    scoped = [c for c in blocking if "--select" in c]
    assert scoped, f"ruff في CI بلا --select: {blocking}"
    for cmd in scoped:
        assert "E9" in cmd and "F82" in cmd, cmd
        assert "--exit-zero" not in cmd, f"خطوة ruff الحرجة مخمَدة: {cmd}"


def test_full_style_ruff_is_explicitly_informational(ci_text):
    """التقرير الأسلوبي الكامل مسموح — لكن فقط إن كان مخمداً صراحةً.

    تُتخطى أسطر التعليقات: شرح القياس يذكر الأمر نفسه كنص، وفحصه كسطر تنفيذي
    إيجابية كاذبة (وقعت فعلاً أثناء كتابة هذا الاختبار).
    """
    for line in _code_lines(ci_text):
        if "ruff check" in line and "--select" not in line:
            assert "--exit-zero" in line, (
                f"ruff غير مقيّد ولا مخمد — سيُحمرّ البناء: {line.strip()}"
            )


def _code_lines(text: str):
    """أسطر YAML التنفيذية فقط (بلا تعليقات)."""
    for line in text.splitlines():
        if line.strip().startswith("#"):
            continue
        yield line


# ---------------------------------------------------------------------------
# 2) تثبيت إصدارات أدوات الفحص
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tool", ["ruff", "mypy"])
def test_lint_tools_are_version_pinned(ci_text, tool):
    assert re.search(rf'"{tool}==[0-9.]+"', ci_text), (
        f"{tool} غير مثبّت الإصدار في CI — نتائج الفحص غير قابلة لإعادة الإنتاج"
    )


# ---------------------------------------------------------------------------
# 3) لا أخضر كاذب على mypy
# ---------------------------------------------------------------------------

def test_mypy_is_not_a_false_green(ci_text):
    """`|| true` على mypy مقبول **فقط** إن كان مقروناً ببوابة حقيقية في الخطوة نفسها.

    لماذا لا نمنع `|| true` منعاً باتاً: GitHub Actions يشغّل `run:` بـ
    `bash -eo pipefail`، فبدون `|| true` يموت الخطوة عند أول خطأ أنواع **قبل**
    مقارنة العدد بخط الأساس. لذلك العبرة ليست بوجود `|| true` بل بغياب البوابة:
    الأخضر الكاذب هو `|| true` **بلا** ratchet، لا `|| true` بذاته.
    """
    step = re.search(
        r"- name: Type check with mypy.*?(?=\n      - name:|\Z)", ci_text, re.S
    )
    assert step, "خطوة mypy مفقودة من ci.yml"
    body = step.group(0)
    assert "mypy src/" in body

    silenced = "|| true" in body or "--exit-zero" in body
    has_gate = (
        "mypy-baseline.txt" in body
        and "exit 1" in body
        and re.search(r'-gt\s+.?\$\{?BASELINE', body) is not None
    )
    if silenced:
        assert has_gate, (
            "mypy مخمد بلا بوابة ratchet — هذا هو الأخضر الكاذب بعينه. "
            "أضف مقارنة بخط الأساس + exit 1، أو أزل `|| true`."
        )


def test_mypy_uses_a_committed_ratchet_baseline(ci_text):
    assert "mypy-baseline.txt" in ci_text, "لا يوجد خط أساس مُودَع لعدد أخطاء mypy"
    assert "COUNT" in ci_text and "BASELINE" in ci_text, "منطق ratchet مفقود"
    assert "exit 1" in ci_text, "ـratchet لا تفشل البناء عند الزيادة"


def test_mypy_baseline_file_is_a_plain_integer():
    assert BASELINE.exists(), f"missing {BASELINE}"
    value = BASELINE.read_text(encoding="utf-8").strip()
    assert value.isdigit(), f"خط الأساس يجب أن يكون عدداً صحيحاً، وجد: {value!r}"
    assert 0 <= int(value) < 10_000


# ---------------------------------------------------------------------------
# 4) المشغّلات
# ---------------------------------------------------------------------------

def test_ci_runs_on_main_and_develop(ci_yaml):
    # PyYAML يحوّل `on` المفتاحية إلى True (خاصية YAML 1.1) — نعالج الحالتين.
    triggers = ci_yaml.get("on", ci_yaml.get(True))
    assert triggers, "لا يوجد قسم `on:` في ci.yml"
    branches = triggers["push"]["branches"]
    assert "main" in branches, branches
    assert "develop" in branches, f"develop مقطوعة من مشغّل push: {branches}"


def test_pull_request_trigger_targets_main(ci_yaml):
    triggers = ci_yaml.get("on", ci_yaml.get(True))
    assert "main" in triggers["pull_request"]["branches"]


# ---------------------------------------------------------------------------
# 5) الأسرار
# ---------------------------------------------------------------------------

def test_no_secret_in_query_string_in_any_workflow():
    """نفس العطل الذي أُصلح في src/ted_fetcher.py — ممنوع في أي workflow."""
    pattern = re.compile(r"[?&](token|api_key|apikey|key|secret|password)=")
    offenders = []
    for wf in sorted(WORKFLOWS.glob("*.yml")):
        for i, line in enumerate(wf.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip().startswith("#"):
                continue
            if pattern.search(line):
                offenders.append(f"{wf.name}:{i}")
    assert offenders == [], f"أسرار في query string: {offenders}"


def test_mutable_action_refs_are_flagged(ci_text):
    """`@master`/`@main` في actions مرجع متحرك = خطر سلسلة توريد.

    هذا اختبار **توعوي**: لا يفشل اليوم (trivy-action ما زال بـ @master)،
    لكنه يوثّق الموضع حتى لا يُنسى. يُرفع إلى فشل بعد تثبيت المرجع.
    """
    mutable = re.findall(r"uses:\s*[\w./-]+@(master|main)\b", ci_text)
    # معروف ومقبول حالياً؛ غيّر هذا الاختبار إلى `assert not mutable` بعد التثبيت.
    assert len(mutable) <= 1, f"مراجع actions متحركة أكثر من المتوقع: {mutable}"
