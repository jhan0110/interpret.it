"""Session state machine.

Pure-Python transition table — does not touch the DB or WS. The gateway's
session manager calls `next_state(...)` and is responsible for persisting
the result and broadcasting `state.change` frames.

States and transitions mirror ARCHITECTURE.md §5 exactly. Any change here
requires updating that table.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

State = Literal[
    "idle",
    "listening",
    "recording",
    "analyzing",
    "feedback",
    "next_segment",
    "complete",
]

Trigger = Literal[
    "session.start",
    "segment.request",
    "playback.finished",
    "audio.submit",
    "analysis.partial",
    "analysis.complete",
    "feedback.next",
    "session.complete",
    "engine.pick_segment",
]


class InvalidTransition(Exception):
    """Raised when a trigger is not valid for the current state."""


@dataclass(frozen=True)
class TransitionResult:
    from_state: State
    to_state: State
    trigger: Trigger
    reason: str


def next_state(
    current: State,
    trigger: Trigger,
    *,
    has_next_segment: bool = True,
    target_reached: bool = False,
) -> TransitionResult:
    """Compute the next state for a trigger.

    Args:
        current: Current session state.
        trigger: Event causing the transition.
        has_next_segment: For `feedback.next` — whether a candidate
            segment exists at the target difficulty.
        target_reached: For `feedback.next` — whether
            session.segment_count has hit the configured target.

    Returns:
        TransitionResult containing from/to states and a human reason.

    Raises:
        InvalidTransition: when the trigger is not valid in `current`.
    """
    # `session.complete` is always valid (operator/learner can bail).
    if trigger == "session.complete":
        if current == "complete":
            raise InvalidTransition("session already complete")
        return TransitionResult(current, "complete", trigger, "user requested complete")

    if current == "idle":
        if trigger == "segment.request":
            return TransitionResult(current, "listening", trigger, "segment requested")

    elif current == "listening":
        if trigger == "playback.finished":
            return TransitionResult(current, "recording", trigger, "playback + delay elapsed")

    elif current == "recording":
        if trigger == "audio.submit":
            return TransitionResult(current, "analyzing", trigger, "audio uploaded")

    elif current == "analyzing":
        if trigger == "analysis.partial":
            return TransitionResult(current, current, trigger, "one pipeline closed")
        if trigger == "analysis.complete":
            return TransitionResult(current, "feedback", trigger, "both pipelines closed")

    elif current == "feedback":
        if trigger == "feedback.next":
            if target_reached:
                return TransitionResult(current, "complete", trigger, "session target reached")
            return TransitionResult(current, "next_segment", trigger, "next segment requested")

    elif current == "next_segment":
        if trigger == "engine.pick_segment":
            if not has_next_segment:
                raise InvalidTransition("no candidate segment available")
            return TransitionResult(current, "listening", trigger, "engine picked segment")

    elif current == "complete":
        # Terminal; only session.complete handled above, which errors.
        pass

    # Treat session.start as a no-op confirmation for clients reconnecting
    # to a session that's already past idle.
    if trigger == "session.start":
        return TransitionResult(current, current, trigger, "session.start reaffirmed")

    raise InvalidTransition(f"trigger {trigger!r} not valid from state {current!r}")
