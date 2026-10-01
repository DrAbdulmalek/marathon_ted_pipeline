# monitor.py — نقطة دخول مراقب القناة
import logging

from src.channel_monitor import ChannelMonitor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

if __name__ == "__main__":
    ChannelMonitor("config/config.yaml").run()
