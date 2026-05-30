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

# Source MUST be present before `pip install .` so setuptools.find can
# locate the `app` package. Without this, only deps land in site-packages
# and the install is a no-op for project code.
COPY pyproject.toml ./
COPY app ./app
COPY scripts ./scripts

# Install CPU-only torch first from the pytorch index to avoid pulling
# ~3 GB of NVIDIA CUDA libraries that we never use on Mac/CPU hosts.
# sentence-transformers model weights (~1 GB for multilingual-e5)
# download lazily on first use, or via:
#     docker compose exec analysis python -m scripts.download_models
RUN pip install --upgrade pip \
    && pip install --index-url https://download.pytorch.org/whl/cpu "torch>=2.2.0" \
    && pip install .

EXPOSE 8001

# Default command runs the FastAPI app; the docker-compose worker
# service overrides with `arq app.worker.WorkerSettings`.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
