FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps: ffmpeg for pydub/librosa decoding, libsndfile for librosa.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

# spaCy language models (referenced in CLAUDE.md; required for Phase 5+).
RUN python -m spacy download ko_core_news_lg && \
    python -m spacy download en_core_web_trf

COPY app ./app

EXPOSE 8001

# Default command runs the FastAPI app; the docker-compose worker
# service overrides with `arq app.worker.WorkerSettings`.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
