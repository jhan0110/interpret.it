"""Tests for the prompt-template loader (front-matter parse + Jinja2 render)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.llm.templates import (
    PROMPTS_DIR,
    PromptCall,
    _split_front_matter,
    render_template,
)


def test_split_front_matter_simple() -> None:
    raw = "---\nmodel: x\nsystem: hi\ntool: {}\n---\nbody here\n"
    meta, body = _split_front_matter(raw)
    assert meta == {"model": "x", "system": "hi", "tool": {}}
    assert body == "body here\n"


def test_split_front_matter_no_front_matter() -> None:
    meta, body = _split_front_matter("just a body\n")
    assert meta == {}
    assert body == "just a body\n"


def test_split_front_matter_unclosed_raises() -> None:
    with pytest.raises(ValueError, match="never closed"):
        _split_front_matter("---\nmodel: x\nbody without close")


def test_generate_segments_template_renders(tmp_path: Path) -> None:
    """The prompt that ships in the repo must render with valid vars."""
    assert (PROMPTS_DIR / "generate_segments.md").is_file()
    call = render_template(
        "generate_segments",
        {
            "n": 10,
            "topic_csv": "logistics",
            "topic_descriptions": ["supply, transport, sustainment"],
            "user_level": 3,
            "user_level_label": "Working",
            "internal_min": 4,
            "internal_max": 7,
            "internal_peak": 5,
            "difficulty_description": "Conversational pace, mixed register.",
            "duration_label": "medium",
            "target_seconds": 20,
            "approx_words": 45,
            "direction_label": "English -> Korean",
            "source_lang": "en",
            "target_lang": "ko",
            "source_lang_long": "English",
            "domain_guidance": "",
            "language_guidance": "",
            "current_context": "",
        },
    )
    assert isinstance(call, PromptCall)
    assert call.tool["name"] == "emit_segments"
    assert "10" in call.user  # n rendered into the user message
    assert "logistics" in call.system
    # Model identifier is OpenRouter-qualified now (e.g.
    # "anthropic/claude-sonnet-4-6"). Assert the family token rather
    # than a strict prefix.
    assert "claude" in call.model.lower()


def test_generate_segments_template_missing_var_strict() -> None:
    with pytest.raises(Exception):  # StrictUndefined raises UndefinedError
        render_template("generate_segments", {})
