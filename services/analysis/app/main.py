"""Analysis FastAPI app.

Most real work runs inside the arq worker (`app.worker`). The HTTP surface
exposes /health + /internal/embed_texts (called by the gateway during
segment seeding to populate `paraphrase_embeddings`).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from fastapi import FastAPI
from pydantic import BaseModel

from app.embeddings import embed_texts

app = FastAPI(title="interpretit-analysis")

_VERSION = os.getenv("ANALYSIS_VERSION", "0.1.0")


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "version": _VERSION,
        "checked_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


class EmbedRequest(BaseModel):
    texts: list[str]


class EmbedResponse(BaseModel):
    embeddings: list[list[float]]


@app.post("/internal/embed_texts", response_model=EmbedResponse)
async def post_embed_texts(req: EmbedRequest) -> EmbedResponse:
    return EmbedResponse(embeddings=embed_texts(req.texts))
