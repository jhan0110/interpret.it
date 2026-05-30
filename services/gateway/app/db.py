"""Async SQLAlchemy session + engine setup.

The async engine's connection pool is bound to whichever asyncio event
loop first opens a connection. To survive (a) pytest creating one loop
per test, (b) arq workers running on their own loop, and (c) the
FastAPI app loop, we key the engine cache by the running event loop's
id and rebuild lazily.

`engine()` / `sessionmaker_factory()` keep their original sync
signatures so the dozens of call sites don't need to change.
"""

from __future__ import annotations

import asyncio
import os
import threading
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_DEFAULT_DSN = "postgresql+asyncpg://interpretit:interpretit@localhost:5432/interpretit"


def database_url() -> str:
    return os.getenv("DATABASE_URL", _DEFAULT_DSN)


_lock = threading.Lock()
_engines: dict[int, AsyncEngine] = {}
_sessionmakers: dict[int, async_sessionmaker[AsyncSession]] = {}


def _loop_key() -> int:
    """Return a stable key for the current asyncio event loop.

    When called from sync code with no running loop (e.g. alembic) we
    fall back to a sentinel so a single shared engine is used.
    """
    try:
        return id(asyncio.get_running_loop())
    except RuntimeError:
        return -1


def _get_engine() -> AsyncEngine:
    key = _loop_key()
    eng = _engines.get(key)
    if eng is not None:
        return eng
    with _lock:
        eng = _engines.get(key)
        if eng is None:
            eng = create_async_engine(database_url(), pool_pre_ping=True, future=True)
            _engines[key] = eng
            _sessionmakers[key] = async_sessionmaker(
                eng, expire_on_commit=False, class_=AsyncSession
            )
    return eng


def _get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    key = _loop_key()
    sm = _sessionmakers.get(key)
    if sm is not None:
        return sm
    _get_engine()  # populates both maps
    return _sessionmakers[_loop_key()]


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a transactional session."""
    sm = _get_sessionmaker()
    async with sm() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


def engine() -> AsyncEngine:
    """Return the async engine for the current event loop."""
    return _get_engine()


def sessionmaker_factory() -> async_sessionmaker[AsyncSession]:
    """Return the sessionmaker for the current event loop."""
    return _get_sessionmaker()


async def dispose() -> None:
    """Dispose engines for the current loop (used by test teardown)."""
    key = _loop_key()
    eng = _engines.pop(key, None)
    _sessionmakers.pop(key, None)
    if eng is not None:
        await eng.dispose()


async def dispose_all() -> None:
    """Dispose every cached engine (FastAPI lifespan shutdown)."""
    with _lock:
        engines = list(_engines.values())
        _engines.clear()
        _sessionmakers.clear()
    for eng in engines:
        await eng.dispose()
