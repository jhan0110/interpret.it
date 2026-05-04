from __future__ import annotations

import pytest

from app.engine.state_machine import (
    InvalidTransition,
    next_state,
)


def test_idle_to_listening_on_segment_request() -> None:
    r = next_state("idle", "segment.request")
    assert r.to_state == "listening"


def test_listening_to_recording_on_playback_finished() -> None:
    r = next_state("listening", "playback.finished")
    assert r.to_state == "recording"


def test_recording_to_analyzing_on_audio_submit() -> None:
    r = next_state("recording", "audio.submit")
    assert r.to_state == "analyzing"


def test_analyzing_partial_keeps_state() -> None:
    r = next_state("analyzing", "analysis.partial")
    assert r.to_state == "analyzing"


def test_analyzing_to_feedback_on_complete() -> None:
    r = next_state("analyzing", "analysis.complete")
    assert r.to_state == "feedback"


def test_feedback_to_next_segment_when_more_remain() -> None:
    r = next_state("feedback", "feedback.next", target_reached=False)
    assert r.to_state == "next_segment"


def test_feedback_to_complete_when_target_reached() -> None:
    r = next_state("feedback", "feedback.next", target_reached=True)
    assert r.to_state == "complete"


def test_next_segment_to_listening() -> None:
    r = next_state("next_segment", "engine.pick_segment", has_next_segment=True)
    assert r.to_state == "listening"


def test_next_segment_without_candidate_raises() -> None:
    with pytest.raises(InvalidTransition):
        next_state("next_segment", "engine.pick_segment", has_next_segment=False)


def test_session_complete_works_from_any_state() -> None:
    for state in ("idle", "listening", "recording", "analyzing", "feedback"):
        r = next_state(state, "session.complete")
        assert r.to_state == "complete"


def test_session_complete_from_complete_raises() -> None:
    with pytest.raises(InvalidTransition):
        next_state("complete", "session.complete")


def test_invalid_trigger_in_state_raises() -> None:
    with pytest.raises(InvalidTransition):
        next_state("idle", "audio.submit")


def test_session_start_is_idempotent_noop() -> None:
    r = next_state("recording", "session.start")
    assert r.to_state == "recording"
    assert "reaffirmed" in r.reason
