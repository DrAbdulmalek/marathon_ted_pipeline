"""
خط أنابيب كامل: صوت → نص → ترجمة → SRT/TXT.
"""
import logging
import subprocess
from pathlib import Path
from typing import Optional, List

from .base import ASRResult
from . import create_engine

logger = logging.getLogger(__name__)


def extract_audio_from_video(video_path: str, output_path: str = None,
                              sample_rate: int = 16000) -> str:
    """استخراج صوت أحادي 16kHz من فيديو."""
    video_path = Path(video_path)
    if output_path is None:
        output_path = str(video_path.with_suffix(".wav"))

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-ac", "1",
        "-ar", str(sample_rate),
        "-vn", output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    logger.info("تم استخراج الصوت: %s", output_path)
    return output_path


def segments_to_srt(segments: List) -> str:
    """تحويل المقاطع إلى SRT."""
    def fmt(t: float) -> str:
        h = int(t // 3600)
        m = int((t % 3600) // 60)
        s = int(t % 60)
        ms = int((t - int(t)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    for i, seg in enumerate(segments, start=1):
        lines.append(str(i))
        lines.append(f"{fmt(seg.start)} --> {fmt(seg.end)}")
        lines.append(seg.text)
        lines.append("")

    return "\n".join(lines)


def segments_to_bilingual_srt(source_segs: List, target_texts: List[str]) -> str:
    """SRT ثنائي اللغة."""
    def fmt(t: float) -> str:
        h = int(t // 3600)
        m = int((t % 3600) // 60)
        s = int(t % 60)
        ms = int((t - int(t)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    for i, seg in enumerate(source_segs, start=1):
        tgt = target_texts[i - 1] if i - 1 < len(target_texts) else ""
        lines.append(str(i))
        lines.append(f"{fmt(seg.start)} --> {fmt(seg.end)}")
        lines.append(seg.text)
        lines.append(tgt)
        lines.append("")

    return "\n".join(lines)


def transcribe_and_translate(
    audio_path: str,
    source_lang: str = "en",
    target_lang: str = "ar",
    asr_engine: str = "whisper-local",
    translator_engine: str = "google",
    output_dir: Optional[str] = None,
    speaker_diarization: bool = False,
) -> dict:
    """
    خط الأنابيب الرئيسي.
    """
    output_dir = Path(output_dir or "data/asr_output")
    output_dir.mkdir(parents=True, exist_ok=True)

    audio_path = Path(audio_path)
    stem = audio_path.stem

    # 1. ASR
    engine = create_engine(asr_engine)
    logger.info("ASR: %s", audio_path.name)
    asr_result: ASRResult = engine.transcribe(
        str(audio_path), language=source_lang
    )

    # 2. ترجمة كل مقطع
    from ..translator import Translator
    tr = Translator(engine=translator_engine)

    target_texts = []
    logger.info("ترجمة %d مقطع...", len(asr_result.segments))
    for seg in asr_result.segments:
        if not seg.text.strip():
            target_texts.append("")
            continue
        try:
            r = tr.translate(seg.text, src=source_lang, tgt=target_lang)
            target_texts.append(r.translated_text)
        except Exception as e:
            logger.warning("فشل ترجمة: %s", e)
            target_texts.append("")

    # 3. مخرجات
    # 3.1 النص الأصلي
    source_txt = output_dir / f"{stem}.{source_lang}.txt"
    source_txt.write_text(asr_result.text, encoding="utf-8")

    # 3.2 الترجمة
    translation_txt = output_dir / f"{stem}.{target_lang}.txt"
    translation_txt.write_text("\n".join(target_texts), encoding="utf-8")

    # 3.3 SRT أحادي
    srt_source = output_dir / f"{stem}.{source_lang}.srt"
    srt_source.write_text(
        segments_to_srt(asr_result.segments), encoding="utf-8"
    )

    # 3.4 SRT ثنائي اللغة
    srt_bilingual = output_dir / f"{stem}.{source_lang}-{target_lang}.srt"
    srt_bilingual.write_text(
        segments_to_bilingual_srt(asr_result.segments, target_texts),
        encoding="utf-8",
    )

    # 3.5 JSON كامل
    import json
    json_out = output_dir / f"{stem}.json"
    json_out.write_text(json.dumps({
        "audio": str(audio_path),
        "source_lang": source_lang,
        "target_lang": target_lang,
        "asr_engine": asr_result.engine,
        "translator_engine": translator_engine,
        "duration": asr_result.duration,
        "segments": [
            {
                "start": s.start, "end": s.end,
                "source": s.text,
                "target": target_texts[i] if i < len(target_texts) else "",
                "speaker": s.speaker,
            }
            for i, s in enumerate(asr_result.segments)
        ],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "source_txt": str(source_txt),
        "translation_txt": str(translation_txt),
        "srt_source": str(srt_source),
        "srt_bilingual": str(srt_bilingual),
        "json": str(json_out),
        "duration": asr_result.duration,
        "segments_count": len(asr_result.segments),
    }
