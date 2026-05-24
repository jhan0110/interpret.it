"""Tests for memorization-mode replay plumbing.

Snapshot + create_session paths are covered via mocked sessionmakers so
the tests do not require a live Postgres. End-to-end WS replay flow is
covered by the M-3 smoke suite.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app import session_manager
from app.api import sessions as sessions_api
from app.contracts.models import PostSessionRequest


def _fake_session_row(**overrides):
    row = SimpleNamespace(
        id=uuid4(),
        learner_id=uuid4(),
        state="idle",
        mode="interpretation",
        domain="logistics",
        source_lang="ko",
        target_lang="en",
        current_segment_id=None,
        segment_count=0,
        planned_segment_ids=None,
        replays_budget=5,
        started_at=datetime.now(UTC),
        completed_at=None,
        generation_params=None,
        generation_state="none",
    )
    for k, v in overrides.items():
        setattr(row, k, v)
    return row


def _scalar_result(value):
    res = MagicMock()
    res.scalar_one_or_none = MagicMock(return_value=value)
    res.scalar_one = MagicMock(return_value=value)
    return res


def _install_fake_sessionmaker(monkeypatch, executes):
    """Patch sessionmaker_factory so each execute() pops from `executes`."""
    db = MagicMock()
    db.execute = AsyncMock(side_effect=list(executes))
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    @asynccontextmanager
    async def _cm():
        yield db

    def _factory():
        return _cm

    monkeypatch.setattr(session_manager, "sessionmaker_factory", _factory)
    return db


@pytest.mark.asyncio
async def test_snapshot_replays_remaining_full_budget(monkeypatch) -> None:
    row = _fake_session_row(mode="memorization", replays_budget=5)
    db = _install_fake_sessionmaker(
        monkeypatch,
        executes=[_scalar_result(row), _scalar_result(0)],
    )
    snap = await session_manager.snapshot(row.id)
    assert snap.mode == "memorization"
    assert snap.replays_remaining == 5
    assert db.execute.await_count == 2


@pytest.mark.asyncio
async def test_snapshot_replays_remaining_decreases(monkeypatch) -> None:
    row = _fake_session_row(mode="memorization", replays_budget=5)
    _install_fake_sessionmaker(
        monkeypatch,
        executes=[_scalar_result(row), _scalar_result(3)],
    )
    snap = await session_manager.snapshot(row.id)
    assert snap.replays_remaining == 2


@pytest.mark.asyncio
async def test_snapshot_replays_remaining_floors_at_zero(monkeypatch) -> None:
    row = _fake_session_row(mode="memorization", replays_budget=2)
    _install_fake_sessionmaker(
        monkeypatch,
        executes=[_scalar_result(row), _scalar_result(7)],
    )
    snap = await session_manager.snapshot(row.id)
    assert snap.replays_remaining == 0


@pytest.mark.asyncio
async def test_snapshot_default_mode_interpretation(monkeypatch) -> None:
    row = _fake_session_row()
    _install_fake_sessionmaker(
        monkeypatch,
        executes=[_scalar_result(row), _scalar_result(0)],
    )
    snap = await session_manager.snapshot(row.id)
    assert snap.mode == "interpretation"
    assert snap.replays_remaining == 5


@pytest.mark.asyncio
async def test_create_session_persists_memorization_mode(monkeypatch) -> None:
    learner_id = uuid4()
    learner = SimpleNamespace(id=learner_id)
    captured: dict = {}

    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(learner))
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    def _add(obj):
        captured["row"] = obj

    db.add = MagicMock(side_effect=_add)

    @asynccontextmanager
    async def _cm():
        yield db

    monkeypatch.setattr(session_manager, "sessionmaker_factory", lambda: _cm)

    row = await session_manager.create_session(
        learner_id=learner_id,
        domain="logistics",
        source_lang="ko",
        target_lang="en",
        mode="memorization",
    )
    assert captured["row"].mode == "memorization"
    assert row.mode == "memorization"


@pytest.mark.asyncio
async def test_create_session_default_mode_interpretation(monkeypatch) -> None:
    learner_id = uuid4()
    learner = SimpleNamespace(id=learner_id)
    captured: dict = {}

    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(learner))
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock(side_effect=lambda obj: captured.setdefault("row", obj))

    @asynccontextmanager
    async def _cm():
        yield db

    monkeypatch.setattr(session_manager, "sessionmaker_factory", lambda: _cm)

    await session_manager.create_session(
        learner_id=learner_id,
        domain="logistics",
        source_lang="ko",
        target_lang="en",
    )
    assert captured["row"].mode == "interpretation"


@pytest.mark.asyncio
async def test_post_session_forwards_mode(monkeypatch) -> None:
    learner_id = uuid4()
    captured: dict = {}

    async def _fake_create_session(**kwargs):
        captured.update(kwargs)
        return _fake_session_row(
            mode=kwargs["mode"],
            learner_id=learner_id,
            domain=kwargs["domain"],
            source_lang=kwargs["source_lang"],
            target_lang=kwargs["target_lang"],
        )

    monkeypatch.setattr(sessions_api, "create_session", _fake_create_session)

    body = PostSessionRequest(
        learner_id=learner_id,
        domain="logistics",
        source_lang="ko",
        target_lang="en",
        mode="memorization",
    )
    out = await sessions_api.post_session(body)
    assert captured["mode"] == "memorization"
    assert out.mode == "memorization"


@pytest.mark.asyncio
async def test_post_session_default_mode_interpretation(monkeypatch) -> None:
    learner_id = uuid4()
    captured: dict = {}

    async def _fake_create_session(**kwargs):
        captured.update(kwargs)
        return _fake_session_row(
            mode=kwargs["mode"],
            learner_id=learner_id,
            domain=kwargs["domain"],
            source_lang=kwargs["source_lang"],
            target_lang=kwargs["target_lang"],
        )

    monkeypatch.setattr(sessions_api, "create_session", _fake_create_session)

    body = PostSessionRequest(
        learner_id=learner_id,
        domain="logistics",
        source_lang="ko",
        target_lang="en",
    )
    out = await sessions_api.post_session(body)
    assert captured["mode"] == "interpretation"
    assert out.mode == "interpretation"
