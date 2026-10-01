import pytest
from pathlib import Path

from src.asr.pipeline import segments_to_srt, segments_to_bilingual_srt
from src.asr.base import TranscriptSegment


def test_segments_to_srt():
    segs = [
        TranscriptSegment(0.0, 2.5, "Hello"),
        TranscriptSegment(2.5, 5.0, "World"),
    ]
    srt = segments_to_srt(segs)
    assert "00:00:00,000 --> 00:00:02,500" in srt
    assert "Hello" in srt
    assert "World" in srt


def test_bilingual_srt():
    segs = [
        TranscriptSegment(0.0, 2.5, "Hello"),
        TranscriptSegment(2.5, 5.0, "World"),
    ]
    targets = ["مرحبا", "عالم"]
    srt = segments_to_bilingual_srt(segs, targets)
    assert "Hello" in srt and "مرحبا" in srt
    assert "World" in srt and "عالم" in srt


def test_srt_time_format():
    segs = [TranscriptSegment(3661.123, 3665.456, "test")]
    srt = segments_to_srt(segs)
    assert "01:01:01,123" in srt
