"""Alembic env — sync engine using the DATABASE_URL with psycopg driver."""

from __future__ import annotations

import logging
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.models.base import Base
from app.models import tables  # noqa: F401  register models with metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

log = logging.getLogger("alembic.env")

# Allow DATABASE_URL env override (for prod / CI).
url = os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
# Alembic runs synchronously — strip asyncpg if present.
if url and "+asyncpg" in url:
    log.info("alembic: rewriting DATABASE_URL '+asyncpg' → '+psycopg' for sync migrations")
    url = url.replace("+asyncpg", "+psycopg")

# Fail loudly if no sync driver is importable rather than failing deep
# inside engine_from_config with a cryptic traceback.
try:
    import psycopg  # type: ignore  # noqa: F401
except ImportError:
    try:
        import psycopg2  # type: ignore  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "alembic requires psycopg (preferred) or psycopg2; install one of them"
        ) from exc

config.set_main_option("sqlalchemy.url", url or "")

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
