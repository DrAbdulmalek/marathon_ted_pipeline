"""اختيار عينات عشوائية من الترجمات لتقييمها."""
import random
import json
import logging
from pathlib import Path
from typing import List, Dict

logger = logging.getLogger(__name__)

DATA_DIR = Path("data/downloads")


def sample_pairs(n: int = 50, seed: int = 42) -> List[Dict]:
    """اختيار n زوج (مصدر، ترجمة) عشوائي."""
    pairs = []
    for f in DATA_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            src = data.get("source_text", "").strip()
            tgt = data.get("target_text", "").strip()
            if src and tgt:
                pairs.append({
                    "source": src,
                    "target": tgt,
                    "file": f.name,
                })
        except Exception:
            continue

    random.seed(seed)
    if len(pairs) <= n:
        return pairs
    return random.sample(pairs, n)
