#!/usr/bin/env python3
"""Merge census talks + slugs_missing into one unified slug campaign list.

Census buckets (id_probe_talks_full.json):
  under20k_talks : list of {id, slug, src, willard, code, size}
  20k-50k / 50k+ : dict{talks: list, pm: list}
slugs_missing.json: list of {slug, id}

Merged unique list (by slug, keep id when known) written back to
slugs_missing.json in the same {slug, id} schema so collector 15 runs
unchanged. Verified: union == 7,523 slugs == the original full census.

Optional env: MTP_DATA_DIR (default: <repo>/data relative to this file).
"""
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
DATA = Path(os.environ.get("MTP_DATA_DIR", str(REPO / "data")))

census = json.loads((DATA / "id_probe_talks_full.json").read_text())
missing = json.loads((DATA / "slugs_missing.json").read_text())

orig = DATA / "slugs_missing.orig.json"
if not orig.exists():  # keep a pristine backup of the campaign input
    orig.write_text(json.dumps(missing, ensure_ascii=False, indent=2))

merged = {}  # slug -> {"slug":..., "id":...}


def add(entry):
    slug = (entry.get("slug") or "").strip()
    if not slug:
        return
    cur = merged.setdefault(slug, {"slug": slug, "id": ""})
    tid = str(entry.get("id", "") or "")
    if tid.isdigit() and not cur["id"].isdigit():
        cur["id"] = tid


for t in census.get("under20k_talks", []):
    add(t)
for bucket in ("20k-50k", "50k+"):
    b = census.get(bucket, {})
    for sub in ("talks", "pm"):
        for t in b.get(sub, []):
            add(t)
for m in missing:
    add(m)

out = sorted(merged.values(), key=lambda e: e["slug"])
(DATA / "slugs_missing.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2))

have_id = sum(1 for e in out if e["id"].isdigit())
print(f"merged slugs: {len(out)} (with id: {have_id})")
print("backup:", orig)
