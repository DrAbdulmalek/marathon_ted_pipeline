"""الواجهة الموحدة لمحركات ASR."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str
    speaker: Optional[str] = None
    confidence: float = 1.0


@dataclass
class ASRResult:
    text: str
    segments: List[TranscriptSegment]
    language: str
    duration: float
    engine: str


class ASREngine(ABC):
    name = "base"

    @abstractmethod
    def transcribe(self, audio_path: str, language: str = "en") -> ASRResult:
        ...

    def is_available(self) -> bool:
        return True
