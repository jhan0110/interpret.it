"""Health endpoint with shallow per-dependency checks."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime

import redis.asyncio as aioredis
from fastapi import APIRouter
from sqlalchemy import text

from app.contracts.models import DependenciesHealth, HealthResponse
from app.db import engine
from app.storage import _client as s3_client  # noqa: PLC2701  intentional internal use

router = APIRouter()

_VERSION = os.getenv("GATEWAY_VERSION", "0.1.0")


async def _check_postgres() -> str:
    try:
        async with engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "down"


async def _check_redis() -> str:
    client = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    try:
        await client.ping()
        return "ok"
    except Exception:
        return "down"
    finally:
        await client.aclose()


async def _check_minio() -> str:
    try:
        await asyncio.to_thread(s3_client().list_buckets)
        return "ok"
    except Exception:
        return "down"


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    pg, rd, mn = await asyncio.gather(_check_postgres(), _check_redis(), _check_minio())
    deps = DependenciesHealth(postgres=pg, redis=rd, minio=mn)  # type: ignore[arg-type]
    if "down" in (pg, rd, mn):
        status = "down" if all(v == "down" for v in (pg, rd, mn)) else "degraded"
    else:
        status = "ok"
    return HealthResponse(
        status=status,  # type: ignore[arg-type]
        version=_VERSION,
        checked_at=datetime.now(UTC),
        dependencies=deps,
    )
