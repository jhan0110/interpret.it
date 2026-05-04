"""Async SQLAlchemy session + engine setup."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_DEFAULT_DSN = "postgresql+asyncpg://interpretit:interpretit@localhost:5432/interpretit"


def database_url() -> str:
    return os.getenv("DATABASE_URL", _DEFAULT_DSN)


_engine = create_async_engine(database_url(), pool_pre_ping=True, future=True)
_sessionmaker = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a transactional session."""
    async with _sessionmaker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


def engine():  # for alembic/migrations
    return _engine


def sessionmaker_factory():  # for arq result-callback paths
    return _sessionmaker
