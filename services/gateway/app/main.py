"""Gateway FastAPI entrypoint.

REST endpoints live under `app.api.*`; the active-session WebSocket lives
in `app.ws.session_socket`. The single writer rule (gateway owns DB
mutations) is enforced by every router going through `session_manager`
or the internal RPC handler — analysis workers never touch the DB.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health, internal, sessions
from app.storage import ensure_bucket
from app.ws import session_socket

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        ensure_bucket()
    except Exception:  # MinIO may not be up yet in some dev flows
        log.warning("ensure_bucket failed at startup", exc_info=True)
    yield


app = FastAPI(title="interpretit-gateway", lifespan=lifespan)

app.include_router(health.router)
app.include_router(sessions.router)
app.include_router(internal.router)
app.include_router(session_socket.router)
