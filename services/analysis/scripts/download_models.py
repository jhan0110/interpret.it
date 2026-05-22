"""One-shot downloader for the large model weights this service uses.

Run after the analysis image is built:

    docker compose exec analysis python -m scripts.download_models

Or set USE_MOCKS=1 (the default) to skip the live embedding model and the
mock hash-based embeddings will be used instead.
"""

from __future__ import annotations

import os
import subprocess
import sys


def _download_spacy(name: str) -> None:
    print(f"spaCy: downloading {name}...")
    subprocess.check_call([sys.executable, "-m", "spacy", "download", name])


def _download_sentence_transformer() -> None:
    name = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-large")
    print(f"sentence-transformers: downloading {name}...")
    from sentence_transformers import SentenceTransformer

    SentenceTransformer(name)


def main() -> None:
    _download_spacy("ko_core_news_lg")
    _download_spacy("en_core_web_trf")
    _download_sentence_transformer()
    print("Done.")


if __name__ == "__main__":
    main()
