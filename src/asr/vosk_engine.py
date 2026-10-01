"""Vosk — خفيف جدًا، يعمل على أجهزة ضعيفة."""
import json
import logging
import wave
from pathlib import Path

from .base import ASREngine, ASRResult, TranscriptSegment

logger = logging.getLogger(__name__)


class VoskEngine(ASREngine):
    name = "vosk"

    def __init__(self, model_path: str):
        try:
            from vosk import Model, KaldiRecognizer, SetLogLevel
        except ImportError:
            raise ImportError("pip install vosk")
        SetLogLevel(-1)
        self.model = Model(model_path)
        self.rec = None

    def transcribe(self, audio_path: str, language: str = "en") -> ASRResult:
        from vosk import KaldiRecognizer
        wf = wave.open(audio_path, "rb")
        if wf.getnchannels() != 1:
            raise ValueError("Vosk يتطلب صوت أحادي القناة")

        rec = KaldiRecognizer(self.model, wf.getframerate())
        rec.SetWords(True)

        segments = []
        texts = []

        while True:
            data = wf.readframes(4000)
            if not data:
                break
            if rec.AcceptWaveform(data):
                r = json.loads(rec.Result())
                if r.get("text"):
                    texts.append(r["text"])
                    if "result" in r:
                        for w in r["result"]:
                            segments.append(TranscriptSegment(
                                start=w["start"], end=w["end"],
                                text=w["word"],
                            ))

        # المقطع الأخير
        r = json.loads(rec.FinalResult())
        if r.get("text"):
            texts.append(r["text"])

        return ASRResult(
            text=" ".join(texts),
            segments=segments,
            language=language,
            duration=wf.getnframes() / wf.getframerate(),
            engine="vosk",
        )
