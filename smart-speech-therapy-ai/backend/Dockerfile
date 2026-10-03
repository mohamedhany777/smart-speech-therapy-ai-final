# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps needed by: psycopg2 (libpq), librosa/soundfile (libsndfile),
# pocketsphinx (compiles its native C library at install time — needs a
# full toolchain and cmake), ffmpeg (video analysis — audio extraction and
# frame sampling), and OpenCV's headless runtime (libgl1/glib for image
# decoding even without a display).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq-dev build-essential cmake curl libsndfile1 libportaudio2 \
        ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/storage /app/qdrant_storage \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Run migrations, then automatically seed default roles/permissions/first
# admin (scripts/seed.py checks for existing data before creating anything,
# so this is always safe to re-run — no manual "open a shell" step needed
# when deploying to a platform like Render). Finally start the API,
# binding to $PORT when the platform provides one (Render/Railway/etc.),
# falling back to 8000 for local/Docker Compose use.
CMD alembic upgrade head && python scripts/seed.py && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
