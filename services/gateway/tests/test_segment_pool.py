"""Pure-logic tests for shared-pool reuse selection + set-id derivation.

The gateway suite has no DB harness, so the `/internal/segment_pool` and
`/internal/generated_set` endpoints are kept as thin glue over these pure
functions (mirrors how `difficulty_ladder` is pure and `segment_picker`
owns the SQL). These cover the no-repeat + accumulation guarantees.
"""

from __future__ import annotations

from uuid import UUID

from app.api.internal import (
    PoolCandidate,
    _generated_set_uuid,
    select_unseen_set,
)


def _uuid(tag: int) -> UUID:
    return UUID(int=tag)


# ── B1: never serve a seen set; None when all seen ──────────────────────


def test_returns_first_unseen() -> None:
    a = PoolCandidate(_uuid(1), ["s0", "s1"], "A")
    b = PoolCandidate(_uuid(2), ["s2", "s3"], "B")
    chosen = select_unseen_set([a, b], seen_ids=set(), n=2)
    assert chosen is a  # newest-first ordering preserved by caller


def test_skips_seen_returns_next() -> None:
    a = PoolCandidate(_uuid(1), ["s0", "s1"], "A")
    b = PoolCandidate(_uuid(2), ["s2", "s3"], "B")
    chosen = select_unseen_set([a, b], seen_ids={_uuid(1)}, n=2)
    assert chosen is b


def test_none_when_all_seen() -> None:
    a = PoolCandidate(_uuid(1), ["s0", "s1"], "A")
    b = PoolCandidate(_uuid(2), ["s2", "s3"], "B")
    assert select_unseen_set([a, b], seen_ids={_uuid(1), _uuid(2)}, n=2) is None


def test_none_when_empty() -> None:
    assert select_unseen_set([], seen_ids=set(), n=2) is None


# ── B10: never serve a set shorter than requested n ─────────────────────


def test_skips_short_sets() -> None:
    short = PoolCandidate(_uuid(1), ["s0", "s1"], "short")  # only 2
    full = PoolCandidate(_uuid(2), ["s0", "s1", "s2", "s3", "s4"], "full")  # 5
    chosen = select_unseen_set([short, full], seen_ids=set(), n=5)
    assert chosen is full


# ── B12: multi-scenario accumulation — returning learner gets a NEW set ─


def test_accumulation_returns_unseen_story() -> None:
    s1 = PoolCandidate(_uuid(10), ["a", "b", "c", "d", "e"], "story-1")
    s2 = PoolCandidate(_uuid(20), ["f", "g", "h", "i", "j"], "story-2")
    # Learner has seen story-1 → gets story-2 (a different cohesive set).
    chosen = select_unseen_set([s1, s2], seen_ids={_uuid(10)}, n=5)
    assert chosen is s2
    # Once both seen → None, so the worker regenerates.
    assert select_unseen_set([s1, s2], seen_ids={_uuid(10), _uuid(20)}, n=5) is None


# ── B6: deterministic, order-independent set id ─────────────────────────


def test_set_id_is_order_independent() -> None:
    ids = ["c-3", "a-1", "b-2"]
    assert _generated_set_uuid(ids) == _generated_set_uuid(list(reversed(ids)))


def test_set_id_stable_and_content_addressed() -> None:
    a = _generated_set_uuid(["x", "y", "z"])
    again = _generated_set_uuid(["x", "y", "z"])
    different = _generated_set_uuid(["x", "y", "w"])
    assert a == again
    assert a != different
    assert isinstance(a, UUID)
