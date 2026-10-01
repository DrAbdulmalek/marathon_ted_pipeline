"""مثال: تنزيل صوت TED وترجمته."""
from src.asr.pipeline import transcribe_and_translate

# 1. نزّل الصوت عبر yt-dlp
import subprocess
subprocess.run([
    "yt-dlp", "-x", "--audio-format", "wav",
    "-o", "data/asr_input/%(id)s.%(ext)s",
    "https://www.ted.com/talks/xxx",
], check=True)

# 2. النسخ والترجمة
result = transcribe_and_translate(
    audio_path="data/asr_input/xxx.wav",
    source_lang="en",
    target_lang="ar",
    asr_engine="whisper-local",
    translator_engine="google",
)
print(result)
