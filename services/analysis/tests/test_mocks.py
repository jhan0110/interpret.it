from __future__ import annotations

from uuid import UUID, uuid4

from app.contracts.models import SemanticResult
from app.mocks.handlers import get_mock_semantic_result


_KNOWN_GOOD = UUID("11111111-1111-1111-1111-111111111111")
_KNOWN_MODERATE = UUID("22222222-2222-2222-2222-222222222222")
_KNOWN_POOR = UUID("33333333-3333-3333-3333-333333333333")


def test_known_good_fixture() -> None:
    r = get_mock_semantic_result(uuid4(), _KNOWN_GOOD)
    assert isinstance(r, SemanticResult)
    assert r.overall_score >= 0.9
    assert r.errors == []


def test_known_moderate_has_errors() -> None:
    r = get_mock_semantic_result(uuid4(), _KNOWN_MODERATE)
    assert 0.5 <= r.overall_score < 0.85
    assert len(r.errors) >= 1


def test_known_poor_has_critical() -> None:
    r = get_mock_semantic_result(uuid4(), _KNOWN_POOR)
    assert r.overall_score < 0.5
    assert any(e.severity == "critical" for e in r.errors)


def test_unknown_segment_falls_back_to_moderate() -> None:
    r = get_mock_semantic_result(uuid4(), uuid4())
    assert r.overall_score > 0
