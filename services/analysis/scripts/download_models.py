"""One-shot downloader for the large model weights this service uses.

Run after the analysis image is built:

    docker compose exec analysis python -m scripts.download_models

Or set USE_MOCKS=1 (the default) to skip the live embedding model and the
mock hash-based embeddings will be used instead.

Earlier versions also downloaded spaCy models for tokenisation; spaCy is
no longer a dependency (we use sentence-transformers tokenisation +
Groq Whisper word-timestamps), so the only weights worth pre-fetching
are the multilingual-e5 embedding model.
"""

from __future__ import annotations

import os


def _download_sentence_transformer() -> None:
    name = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-large")
    print(f"sentence-transformers: downloading {name}...")
    from sentence_transformers import SentenceTransformer

    SentenceTransformer(name)


def main() -> None:
    _download_sentence_transformer()
    print("Done.")


if __name__ == "__main__":
    main()
