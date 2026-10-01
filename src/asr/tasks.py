"""مهام ASR للـ worker."""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def asr_task(audio_path: str, source_lang: str, target_lang: str) -> dict:
    """مهمة RQ."""
    from .pipeline import transcribe_and_translate, extract_audio_from_video
    from ..webhooks import fire_event

    try:
        p = Path(audio_path)
        if p.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov"):
            audio = extract_audio_from_video(audio_path)
        else:
            audio = audio_path

        result = transcribe_and_translate(
            audio_path=audio,
            source_lang=source_lang,
            target_lang=target_lang,
        )

        fire_event("asr.completed", {
            "audio": audio_path,
            "result": result,
        })
        return result
    except Exception as e:
        fire_event("asr.failed", {
            "audio": audio_path,
            "error": str(e),
        })
        raise
