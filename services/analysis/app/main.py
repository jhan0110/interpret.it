"""Analysis FastAPI app.

Exposes only /health. All real work runs inside the arq worker
(`app.worker`); the HTTP surface is for liveness probes and on-demand
admin tools.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from fastapi import FastAPI

app = FastAPI(title="interpretit-analysis")

_VERSION = os.getenv("ANALYSIS_VERSION", "0.1.0")


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "version": _VERSION,
        "checked_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
