# Migrate OCR rules to Visual Evidence Charter + CWD-independent paths

> **ملخص عربي**: ترحيل قواعد OCR من v1 التنظيفي إلى ميثاق الدليل البصري v2، مع حفظ عقد v1 (مبدأ superset)، وإصلاح استقلالية المسارات عن دليل التشغيل (CWD)، ودعم اتجاه الترجمة ar↔en، وتثبيت أول دليل بايتي حي من TED كـ fixture دائم. 6 commits على `main` (7e90498)، لا يكسر أي عقد قائم.

## What this PR does

Six commits migrating the OCR subsystem to the Visual Evidence Charter (v2)
while preserving every v1 contract (superset principle — add, never break),
plus infrastructure fixes that make config paths CWD-independent and CI lint
signal-bearing (real errors only, not the 344-item legacy style debt).

## Commits (in order)

| # | SHA | Subject |
|---|-----|---------|
| 1 | `c57c67f` | MIGRATION: Visual Evidence Charter v2 — REPLACE ocr rules + EXTEND processor (+1147/−203, 9 files) |
| 2 | `3307496` | FIX(R14): sync charter visual markers into v1 engine under v2 (union, not replace) |
| 3 | `25c076c` | FIX(lang): Arabic-English support — registry, contracts, direction logic (11 languages) |
| 4 | `6eaf79f` | FIX(infra): CWD-independent registry + CI lint triage (E9,F63,F7,F82 only) |
| 5 | `a55ae55` | FIX(paths): CWD-independent config paths in api.py + dashboard.py |
| 6 | `b933cd2` | TEST(evidence): permanent E2E fixture — first real bytes from TED |

## Key changes

### 1. Visual Evidence Charter v2 (`config/marathon_ocr_rules.yaml`, `src/ocr_processor.py`)
- v2 charter rules replace the v1 cleaning rules as the primary rule set.
- v1 is **preserved** as `config/text_normalization_rules.yaml` (pre-pass stage).
- R14 fix: charter visual markers (`✓ ✔ ✗ ✘ X x ✖ ❌ ☑`) are synced into the
  v1 engine **by union** — v1 behaviour never regresses.
- New v2 concepts wired in: uncertainty states
  (`COLOR_SEMANTICS_UNCERTAIN`, `VISUAL_INTERPRETATION_UNCERTAIN`,
  `VISUAL_CONFIDENCE_LOW`), labels (`EXAMPLE_OF_ERROR`,
  `INCORRECT_EXAMPLE`, `VISUAL_CORRECTION_EXAMPLE`, `POSITIVE_EXAMPLE`),
  and the visual metadata schema separating
  `positive_example` ≠ `negative_example` in training data.
- `scripts/verify_migration.py` added as an offline migration verifier.

### 2. Translation direction ar↔en (`src/translator.py`, `src/ted_fetcher.py`, `config/languages.yaml`)
- Registry extended to 11 languages including `en`.
- Direction logic handles ar→en as a first-class pair (not only en→ar).

### 3. CWD-independent paths (`src/languages.py`, `src/api.py`, `dashboard.py`)
- All three derive paths from `Path(__file__)`, not the working directory.
- Environment overrides are **preserved**: `LANGUAGES_FILE` (languages.py),
  `CONFIG_PATH` (api.py, pre-existing contract kept by superset principle),
  `MARATHON_CONFIG` (dashboard.py — root-level file needs `.parent`, not
  `.parent.parent`).
- Proven live: `src.api` imports successfully from a CWD outside the repo
  (subprocess-based regression test with isolated DB data).

### 4. CI lint triage (`.github/workflows/ci.yml`)
- `ruff check src/ tests/ --select E9,F63,F7,F82 --ignore E501`
- Real errors only (undefined names, f-string placeholders, syntax). The full
  ruff sweep reports 344 inherited style findings from `main` — that debt is
  deliberately **not** mixed into this PR (separate cleanup PR planned).

### 5. Permanent evidence fixture (`data/evidence/talk_8593_ar.vtt`)
- 16,710 bytes of real Arabic WEBVTT, fetched live from
  `hls.ted.com/project_masters/8593/subtitles/ar/full.vtt` (HTTP 200).
- First real bytes from TED in this repo's history.
- `tests/test_evidence_fixture.py` locks it with 3 tests: size ≥ 16 KB,
  WEBVTT structure + timestamps, > 500 Arabic characters — silent replacement
  of the evidence is now impossible.

## Test evidence (byte-level)

- **pytest (junitxml)**: `tests=94 failures=0 errors=0 skipped=1`
  (baseline on `main` was 61 passed / 1 skipped → +33 tests, all committed
  with their commit).
- **ruff (CI gate)**: `ruff check src/ tests/ --select E9,F63,F7,F82 --ignore E501`
  → exit 0 locally on this branch.
- `git bundle verify` on the full branch bundle: OK, base = `main` (7e90498) only.
- Live byte-proof of the subtitle endpoint: HTTP 200, 16,710 B Arabic VTT,
  sample committed as the fixture above.

## Reviewer checklist

- [ ] `marathon_ocr_rules.yaml` v2 semantics read as charter (not cleaning) rules
- [ ] `text_normalization_rules.yaml` is byte-identical to the old v1 content
- [ ] `api.py` keeps the pre-existing `CONFIG_PATH` env override contract
- [ ] `dashboard.py` uses `.parent` (root file) — `.parent.parent` would escape the repo
- [ ] `ci.yml` triggers unchanged (`push: [main, develop]` + PRs to `main`)
- [ ] Fixture tests actually fail if `data/evidence/talk_8593_ar.vtt` is swapped for a stub

## What this PR deliberately does NOT do

- No merge to production services without E2E (Docker/Redis/Telegram flows are
  untested here — Alpha is honest: verified at unit level, not system level).
- No ruff style-debt cleanup (344 findings — separate PR after this merges).
- No changes to `main`-owned deploy workflows.
