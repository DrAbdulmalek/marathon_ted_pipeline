# Dockerfile — Marathon TED Pipeline
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# ---------- اعتماديات النظامية ----------
# tesseract + لغاته للـ OCR، ffmpeg للـ ASR، libpq لـ psycopg
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-ara \
    tesseract-ocr-eng \
    ffmpeg \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# ---------- اعتماديات بايثون ----------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------- المشروع ----------
COPY src/ ./src/
COPY config/ ./config/
COPY run.py monitor.py api.py bot.py dashboard.py manage_auth.py ./
COPY ted2srt_py/ ./ted2srt_py/

# مجلدات البيانات
RUN mkdir -p data/downloads data/logs

EXPOSE 8000 8501

CMD ["python", "run.py"]
