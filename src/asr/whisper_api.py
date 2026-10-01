"""Whisper API (OpenAI) — سريع بدون GPU."""
import os
import logging
from pathlib import Path

from .base import ASREngine, ASRResult, TranscriptSegment

logger = logging.getLogger(__name__)


class WhisperAPIEngine(ASREngine):
    name = "whisper-api"

    def __init__(self, api_key: str = None):
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("pip install openai")
        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise ValueError("OPENAI_API_KEY مطلوب")
        self.client = OpenAI(api_key=key)

    def transcribe(self, audio_path: str, language: str = "en") -> ASRResult:
        logger.info("Whisper API: نسخ %s", audio_path)
        with open(audio_path, "rb") as f:
            resp = self.client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language=language,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )

        segments = []
        for s in resp.segments:
            segments.append(TranscriptSegment(
                start=s.start, end=s.end, text=s.text.strip(),
            ))

        return ASRResult(
            text=resp.text,
            segments=segments,
            language=resp.language,
            duration=getattr(resp, "duration", 0.0),
            engine="whisper-api",
        )
