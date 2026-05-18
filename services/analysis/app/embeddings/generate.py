"""Sentence-transformers embedding generation.

Uses multilingual-e5-large (1024-dim) to embed paraphrase texts.
The model is loaded once at first call and cached for the process lifetime.
Dimension must match EMBEDDING_DIM = 1024 in the gateway's models/tables.py.
"""

from __future__ import annotations

import logging
from functools import lru_cache

log = logging.getLogger(__name__)

_MODEL_NAME = "intfloat/multilingual-e5-large"


@lru_cache(maxsize=1)
def _get_model():
    from sentence_transformers import SentenceTransformer

    log.info("loading sentence-transformers model %s", _MODEL_NAME)
    model = SentenceTransformer(_MODEL_NAME)
    log.info("sentence-transformers model loaded")
    return model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Return a list of 1024-dim unit-normed embeddings, one per input text."""
    model = _get_model()
    # e5 models expect "query: " or "passage: " prefixes for best results.
    prefixed = [f"passage: {t}" for t in texts]
    vectors = model.encode(prefixed, normalize_embeddings=True)
    return [v.tolist() for v in vectors]
