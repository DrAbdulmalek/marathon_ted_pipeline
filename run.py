# run.py — نقطة دخول المنسّق الرئيسي (مراقبة مستمرة)
import logging

from src.marathon_runner import MarathonRunner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

if __name__ == "__main__":
    MarathonRunner("config/config.yaml").start()
