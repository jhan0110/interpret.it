"""Evaluation runs on the faster EVAL_MODEL (Haiku) by default, overridable.

Locks in the latency optimization: scoring uses a faster model than
reference/generation, measured ~2x faster with calibration preserved.
Mocks at the LLM trust boundary (structured_generate); the stub takes
**kwargs so production signature drift can't break it (R24).
"""

from __future__ import annotations

import importlib
from datetime import datetime, timezone
from uuid import uuid4

from app.reference.generate import ReferenceBundle

# import_module returns the actual submodule even though the package
# re-exports the `evaluate` function under the same name.
ev = importlib.import_module("app.evaluation.evaluate")

_VALID_TOOL_OUT = {
    "errors": [],
    "overall_score": 0.8,
    "feedback_text": "Good rendition.",
    "followup_exercise": {"type": "repeat", "prompt_text": "Try again."},
}


def _run(monkeypatch) -> str:
    captured: dict = {}

    def fake_structured_generate(**kwargs):
        captured.update(kwargs)
        return dict(_VALID_TOOL_OUT)

    monkeypatch.setattr(ev, "structured_generate", fake_structured_generate)
    ev.evaluate(
        uuid4(),
        "source text",
        "en",
        "ko",
        "formal-military",
        "logistics",
        5,
        "learner transcript",
        ReferenceBundle(canonical="ref", paraphrases=["p1"]),
        "fb.mp3",
        "fu.mp3",
        datetime.now(timezone.utc),
    )
    return captured["model"]


def test_eval_defaults_to_haiku(monkeypatch) -> None:
    monkeypatch.delenv("EVAL_MODEL", raising=False)
    assert _run(monkeypatch) == "anthropic/claude-haiku-4-5"


def test_eval_model_env_override(monkeypatch) -> None:
    monkeypatch.setenv("EVAL_MODEL", "anthropic/claude-sonnet-4-6")
    assert _run(monkeypatch) == "anthropic/claude-sonnet-4-6"
