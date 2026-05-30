"""Difficulty ladder + mastery update logic.

Implements ARCHITECTURE.md §6 verbatim. Pure functions — segment selection
takes already-fetched candidate lists and learner history; SQL is done in
the caller (gateway api/engine glue).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

try:  # numpy is in the gateway image but optional for the model fallback
    import numpy as _np  # type: ignore[import-not-found]

    _HAS_NUMPY = True
except ImportError:
    _np = None  # type: ignore[assignment]
    _HAS_NUMPY = False

CognitiveLoad = Literal["low", "moderate", "high", "overloaded"]

_PROSODY_SCORE_MAP: dict[CognitiveLoad, float] = {
    "low": 1.0,
    "moderate": 0.75,
    "high": 0.40,
    "overloaded": 0.10,
}


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def combined_score(semantic_overall: float | None, cognitive_load: CognitiveLoad | None) -> float:
    """Blend semantic and prosody scores. Missing component contributes neutrally."""
    if semantic_overall is None and cognitive_load is None:
        return 0.0
    sem = semantic_overall if semantic_overall is not None else 0.5
    pros = _PROSODY_SCORE_MAP[cognitive_load] if cognitive_load is not None else 0.5
    return _clamp01(0.7 * sem + 0.3 * pros)


def update_mastery(
    old_mastery: float,
    attempts_count: int,
    score: float,
) -> float:
    """EMA mastery update — α decays with attempts but floors at 0.15."""
    alpha = max(0.15, 1.0 / (1 + attempts_count))
    return _clamp01(old_mastery + alpha * (score - old_mastery))


def difficulty_delta(old_mastery: float, new_mastery: float) -> int:
    if new_mastery > old_mastery and new_mastery >= 0.80:
        return +1
    if new_mastery < old_mastery and new_mastery < 0.50:
        return -1
    return 0


def target_level(current_level: int, delta: int) -> int:
    return max(1, min(10, current_level + delta))


@dataclass(frozen=True)
class CandidateSegment:
    """Minimal segment view used by the selector."""

    id: UUID
    difficulty_level: int
    domain: str
    register: str
    source_lang: str
    target_lang: str
    embedding: list[float] | None  # may be None when paraphrase embedding not yet generated


@dataclass(frozen=True)
class LearnerHistoryItem:
    segment_id: UUID
    recent_score: float  # rolling avg on this segment, 0.0-1.0
    last_seen_embedding: list[float] | None


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity. numpy path is ~50× faster on 1024-d vectors."""
    if _HAS_NUMPY:
        av = _np.asarray(a, dtype=_np.float32)
        bv = _np.asarray(b, dtype=_np.float32)
        na = float(_np.linalg.norm(av))
        nb = float(_np.linalg.norm(bv))
        if na == 0.0 or nb == 0.0:
            return 0.0
        return float(_np.dot(av, bv) / (na * nb))
    num = sum(x * y for x, y in zip(a, b, strict=False))
    da = sum(x * x for x in a) ** 0.5
    db = sum(y * y for y in b) ** 0.5
    if da == 0 or db == 0:
        return 0.0
    return num / (da * db)


def select_next_segment(
    candidates: list[CandidateSegment],
    recent_segment_ids: set[UUID],
    recent_embeddings: list[list[float]],
    history: dict[UUID, LearnerHistoryItem],
    *,
    similarity_threshold: float = 0.92,
    rng: random.Random | None = None,
) -> CandidateSegment | None:
    """Apply recency → novelty → mastery-weighted sampling.

    Returns None when no candidate survives — caller handles the fallback
    cascade (relax filters, widen to ±1 level).
    """
    rng = rng or random.Random()

    pool = [c for c in candidates if c.id not in recent_segment_ids]
    if not pool:
        return None

    if recent_embeddings:
        kept: list[CandidateSegment] = []
        for c in pool:
            if c.embedding is None:
                kept.append(c)
                continue
            too_similar = any(
                _cosine(c.embedding, ref) > similarity_threshold for ref in recent_embeddings
            )
            if not too_similar:
                kept.append(c)
        pool = kept

    if not pool:
        return None

    weights = []
    for c in pool:
        prior = history.get(c.id)
        proxy = prior.recent_score if prior is not None else 0.5
        weights.append(max(0.01, 1.0 - proxy))

    return rng.choices(pool, weights=weights, k=1)[0]


def can_promote_above_8(attempts_at_level: int, mean_score_at_level: float) -> bool:
    """Anti-fluke gate for promotion from level 8 → 9."""
    return attempts_at_level >= 3 and mean_score_at_level >= 0.75


def target_level_from_mastery(mastery: float) -> int:
    """Map a [0,1] mastery score onto the 1..10 ladder.

    Linear: 0.0 → 1, 1.0 → 10. A first-time learner (default 0.5) lands
    near the middle of the ladder, matching the operator-facing seed data.
    """
    return max(1, min(10, int(round(1 + mastery * 9))))


@dataclass(frozen=True)
class AttemptScoreView:
    """Minimal projection of an AttemptRow needed to roll up segment history.

    Decoupling from SQLAlchemy keeps `difficulty_ladder.py` pure-Python and
    importable from environments that do not have the DB stack installed.
    """

    segment_id: UUID
    overall_score: float | None


def aggregate_history(
    attempts: list[AttemptScoreView],
) -> dict[UUID, LearnerHistoryItem]:
    """Average per-segment scores into a `select_next_segment`-compatible map.

    Attempts whose `overall_score` is None are skipped, which keeps an
    unscored attempt from biasing the weighted-random selector.
    """
    by_seg: dict[UUID, list[float]] = {}
    for a in attempts:
        if a.overall_score is None:
            continue
        by_seg.setdefault(a.segment_id, []).append(float(a.overall_score))
    history: dict[UUID, LearnerHistoryItem] = {}
    for seg_id, scores in by_seg.items():
        avg = sum(scores) / len(scores)
        history[seg_id] = LearnerHistoryItem(
            segment_id=seg_id, recent_score=avg, last_seen_embedding=None
        )
    return history
