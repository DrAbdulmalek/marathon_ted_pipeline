from .base import ASREngine, ASRResult, TranscriptSegment

_ENGINES = {}


def register_engine(name: str, cls):
    _ENGINES[name] = cls


def get_engine(name: str, **kwargs) -> ASREngine:
    if name not in _ENGINES:
        raise ValueError(f"محرك ASR غير معروف: {name}")
    return _ENGINES[name](**kwargs)


def create_engine(engine: str = "whisper-local", **kwargs) -> ASREngine:
    """مصنع يختار أفضل محرك متاح."""
    if engine == "whisper-local":
        try:
            from .whisper_local import WhisperLocalEngine
            return WhisperLocalEngine(**kwargs)
        except ImportError:
            pass

    if engine == "whisper-api":
        try:
            from .whisper_api import WhisperAPIEngine
            return WhisperAPIEngine(**kwargs)
        except (ImportError, ValueError):
            pass

    if engine == "vosk":
        from .vosk_engine import VoskEngine
        return VoskEngine(**kwargs)

    raise ValueError(f"لا يمكن إنشاء محرك: {engine}")
