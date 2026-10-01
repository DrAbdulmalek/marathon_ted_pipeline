"""Whisper محلي (OpenAI) — الأفضل للخصوصية والجودة."""
import logging
from pathlib import Path
from typing import Optional

from .base import ASREngine, ASRResult, TranscriptSegment

logger = logging.getLogger(__name__)


class WhisperLocalEngine(ASREngine):
    name = "whisper-local"

    def __init__(self, model_size: str = "base",
                 device: str = "auto",
                 compute_type: str = "int8"):
        """
        model_size: tiny|base|small|medium|large-v3
        device: auto|cpu|cuda
        """
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise ImportError(
                "pip install faster-whisper"
            )

        if device == "auto":
            try:
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                device = "cpu"

        self.model_size = model_size
        self.device = device
        self.model = WhisperModel(
            model_size, device=device, compute_type=compute_type,
        )
        logger.info("تم تحميل Whisper %s على %s", model_size, device)

    def transcribe(self, audio_path: str, language: str = "en") -> ASRResult:
        logger.info("Whisper: نسخ %s", audio_path)
        segments_iter, info = self.model.transcribe(
            audio_path,
            language=language,
            beam_size=5,
            vad_filter=True,
            word_timestamps=False,
        )

        segments = []
        texts = []
        for s in segments_iter:
            segments.append(TranscriptSegment(
                start=s.start, end=s.end,
                text=s.text.strip(),
                confidence=1.0,   # Whisper لا يعطي ثقة صريحة
            ))
            texts.append(s.text.strip())

        return ASRResult(
            text=" ".join(texts),
            segments=segments,
            language=info.language,
            duration=info.duration,
            engine=f"whisper-{self.model_size}",
        )
