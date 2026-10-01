"""
تدريب نموذج ترجمة على بيانات TED.
يدعم MarianMT و NLLB.
"""
import os
import logging
from pathlib import Path

import torch
from datasets import load_from_disk
from transformers import (
    AutoTokenizer, AutoModelForSeq2SeqLM,
    DataCollatorForSeq2Seq,
    Seq2SeqTrainingArguments, Seq2SeqTrainer,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------- الإعدادات ----------
MODEL_NAME = os.getenv("BASE_MODEL", "Helsinki-NLP/opus-mt-en-ar")
DATA_DIR = Path("finetune/data/ted_ar_en")
OUTPUT_DIR = Path("finetune/models/ted_ar_v1")
SRC_LANG = "en"
TGT_LANG = "ar"
MAX_LEN = 256
BATCH_SIZE = 16
EPOCHS = 3
LR = 2e-5

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def preprocess(example, tokenizer):
    inputs = tokenizer(
        example["source"], max_length=MAX_LEN,
        truncation=True, padding=False,
    )
    with tokenizer.as_target_tokenizer():
        labels = tokenizer(
            example["target"], max_length=MAX_LEN,
            truncation=True, padding=False,
        )
    inputs["labels"] = labels["input_ids"]
    return inputs


def main():
    logger.info("تحميل Dataset...")
    ds = load_from_disk(str(DATA_DIR))
    logger.info("train: %d, val: %d, test: %d",
                len(ds["train"]), len(ds["validation"]), len(ds["test"]))

    logger.info("تحميل النموذج: %s", MODEL_NAME)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)

    # Tokenize
    logger.info("Tokenizing...")
    tokenized = ds.map(
        lambda ex: preprocess(ex, tokenizer),
        batched=True,
        remove_columns=ds["train"].column_names,
    )

    collator = DataCollatorForSeq2Seq(tokenizer, model=model)

    training_args = Seq2SeqTrainingArguments(
        output_dir=str(OUTPUT_DIR),
        num_train_epochs=EPOCHS,
        per_device_train_batch_size=BATCH_SIZE,
        per_device_eval_batch_size=BATCH_SIZE,
        learning_rate=LR,
        warmup_steps=500,
        weight_decay=0.01,
        logging_dir=str(OUTPUT_DIR / "logs"),
        logging_steps=100,
        eval_strategy="steps",
        eval_steps=500,
        save_steps=1000,
        save_total_limit=2,
        predict_with_generate=True,
        generation_max_length=MAX_LEN,
        fp16=torch.cuda.is_available(),
        gradient_accumulation_steps=2,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        report_to=["tensorboard"],
    )

    trainer = Seq2SeqTrainer(
        model=model,
        args=training_args,
        train_dataset=tokenized["train"],
        eval_dataset=tokenized["validation"],
        tokenizer=tokenizer,
        data_collator=collator,
    )

    logger.info("بدء التدريب...")
    trainer.train()

    logger.info("حفظ النموذج النهائي في: %s", OUTPUT_DIR)
    trainer.save_model(str(OUTPUT_DIR))
    tokenizer.save_pretrained(str(OUTPUT_DIR))

    # اختبار
    logger.info("اختبار على عينة:")
    sample = ds["test"][0]
    inputs = tokenizer(sample["source"], return_tensors="pt").to(model.device)
    out = model.generate(**inputs, max_length=MAX_LEN)
    pred = tokenizer.decode(out[0], skip_special_tokens=True)
    logger.info("SRC : %s", sample["source"])
    logger.info("REF : %s", sample["target"])
    logger.info("PRED: %s", pred)


if __name__ == "__main__":
    main()
