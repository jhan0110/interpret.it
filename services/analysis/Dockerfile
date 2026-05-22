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
# Install CPU-only torch first from the pytorch index to avoid pulling
# ~3 GB of NVIDIA CUDA libraries that we never use on Mac/CPU hosts.
RUN pip install --upgrade pip \
    && pip install --index-url https://download.pytorch.org/whl/cpu "torch>=2.2.0" \
    && pip install .

# spaCy + sentence-transformers libraries are installed via pyproject above.
# The model weights are large (~1 GB combined for spaCy ko+en, ~1 GB for
# multilingual-e5) so they download lazily on first use, or via the helper:
#     docker compose exec analysis python -m scripts.download_models
# Run that once after build; the models cache in /root/.cache and persist
# across container restarts via the named volume if you mount one.

# spaCy language models (referenced in CLAUDE.md; required for Phase 5+).
RUN python -m spacy download ko_core_news_lg && \
    python -m spacy download en_core_web_trf

COPY app ./app
COPY scripts ./scripts

EXPOSE 8001

# Default command runs the FastAPI app; the docker-compose worker
# service overrides with `arq app.worker.WorkerSettings`.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
