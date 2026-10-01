"""تقييم النموذج بـ BLEU و chrF و METEOR."""
import logging
from pathlib import Path

import torch
from datasets import load_from_disk
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
from evaluate import load
from tqdm import tqdm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL_DIR = Path("finetune/models/ted_ar_v1")
DATA_DIR = Path("finetune/data/ted_ar_en")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
MAX_LEN = 256


def main():
    logger.info("تحميل النموذج من: %s", MODEL_DIR)
    tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR))
    model = AutoModelForSeq2SeqLM.from_pretrained(str(MODEL_DIR)).to(DEVICE)
    model.eval()

    ds = load_from_disk(str(DATA_DIR))["test"]
    logger.info("عدد عينات الاختبار: %d", len(ds))

    bleu = load("bleu")
    chrf = load("chrf")
    meteor = load("meteor")

    preds, refs = [], []
    for sample in tqdm(ds):
        inputs = tokenizer(
            sample["source"], return_tensors="pt",
            truncation=True, max_length=MAX_LEN,
        ).to(DEVICE)
        with torch.no_grad():
            out = model.generate(**inputs, max_length=MAX_LEN)
        pred = tokenizer.decode(out[0], skip_special_tokens=True)
        preds.append(pred)
        refs.append(sample["target"])

    logger.info("BLEU  : %.2f", bleu.compute(predictions=preds, references=[[r] for r in refs])["bleu"] * 100)
    logger.info("chrF  : %.2f", chrf.compute(predictions=preds, references=refs)["score"])
    logger.info("METEOR: %.2f", meteor.compute(predictions=preds, references=refs)["meteor"] * 100)

    # أمثلة
    print("\n--- أمثلة ---")
    for i in range(min(5, len(preds))):
        print(f"\nSRC : {ds[i]['source']}")
        print(f"REF : {refs[i]}")
        print(f"PRED: {preds[i]}")


if __name__ == "__main__":
    main()
