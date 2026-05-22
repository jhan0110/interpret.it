"""Sentence-transformers embedding helpers.

Used by the gateway during segment seeding to populate `paraphrase_embeddings`.
Kept thin: model loader + a single `embed_texts` function. Production live-
embedding (per-request) would route through here too.

`USE_MOCKS=1` swaps in a deterministic mock so the dev loop works without
pulling the ~1 GB multilingual-e5 weights.
"""

from __future__ import annotations

import hashlib
import os
from functools import lru_cache

EMBEDDING_DIM = 1024
MODEL_NAME = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-large")


def _use_mocks() -> bool:
    return os.getenv("USE_MOCKS", "1") == "1"


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer  # noqa: WPS433

    return SentenceTransformer(MODEL_NAME)


def _mock_embed(text: str) -> list[float]:
    """Deterministic mock — hash the text into a unit-normalised 1024-vector.

    Stable for the same input so the picker's novelty filter behaves
    repeatably in mock mode, while still distinguishing different inputs.
    """
    digest = hashlib.sha512(text.encode("utf-8")).digest()
    raw = [(digest[i % len(digest)] - 128) / 128.0 for i in range(EMBEDDING_DIM)]
    norm = sum(x * x for x in raw) ** 0.5 or 1.0
    return [x / norm for x in raw]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Return one embedding per input text. Order preserved."""
    if not texts:
        return []
    if _use_mocks():
        return [_mock_embed(t) for t in texts]
    model = _model()
    # multilingual-e5 expects a `passage: ` prefix for indexed text.
    prefixed = [f"passage: {t}" for t in texts]
    vectors = model.encode(prefixed, normalize_embeddings=True)
    return [list(map(float, v)) for v in vectors]
