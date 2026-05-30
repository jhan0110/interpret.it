"""Markdown + YAML-front-matter + Jinja2 prompt loader.

Each prompt template lives in `services/analysis/app/llm/prompts/<name>.md`
and looks like::

    ---
    model: anthropic/claude-sonnet-4-6
    temperature: 0.8
    max_tokens: 4096
    system: |
      You are ...
    tool:
      name: emit_segments
      description: ...
      input_schema: { ... }
    ---
    User-message body, Jinja2-rendered with the variables passed to
    `render_template`.

The loader re-reads the file on every call so prompt edits take effect
without a service restart. This is deliberately not cached.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from jinja2 import Environment, StrictUndefined

from app.llm.client import structured_generate

log = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"
FRONT_MATTER_DELIMITER = "---"


@dataclass(frozen=True)
class PromptCall:
    name: str
    model: str
    temperature: float
    max_tokens: int
    system: str
    user: str
    tool: dict


def _split_front_matter(text: str) -> tuple[dict, str]:
    """Pull a leading ``---\\n…\\n---\\n`` YAML block off the top of `text`.

    Returns `(metadata_dict, body)`. If no front-matter is present, returns
    `({}, text)`.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != FRONT_MATTER_DELIMITER:
        return {}, text
    closing_idx: int | None = None
    for i in range(1, len(lines)):
        if lines[i].strip() == FRONT_MATTER_DELIMITER:
            closing_idx = i
            break
    if closing_idx is None:
        raise ValueError("front-matter opened but never closed with ---")
    fm_text = "".join(lines[1:closing_idx])
    body = "".join(lines[closing_idx + 1 :])
    meta = yaml.safe_load(fm_text) or {}
    if not isinstance(meta, dict):
        raise ValueError("front-matter must be a YAML mapping")
    return meta, body


def _env() -> Environment:
    # Re-construct every call so template overrides land immediately.
    return Environment(
        autoescape=False,  # noqa: S701 — these prompts are not HTML
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )


def _split_raw_front_matter(text: str) -> tuple[str, str]:
    """Return `(front_matter_text, body)` without parsing YAML.

    The front-matter may contain Jinja2 expressions (e.g. ``minItems:
    {{ n }}``) that aren't valid YAML on their own — we need to render
    them with the caller's variables BEFORE handing the result to
    `yaml.safe_load`.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != FRONT_MATTER_DELIMITER:
        return "", text
    closing_idx: int | None = None
    for i in range(1, len(lines)):
        if lines[i].strip() == FRONT_MATTER_DELIMITER:
            closing_idx = i
            break
    if closing_idx is None:
        raise ValueError("front-matter opened but never closed with ---")
    return "".join(lines[1:closing_idx]), "".join(lines[closing_idx + 1 :])


def render_template(name: str, variables: dict) -> PromptCall:
    """Load `prompts/<name>.md`, Jinja2-render the system+user+tool, return PromptCall.

    The front-matter is rendered AS TEXT (with Jinja2) before YAML
    parsing, so expressions like ``minItems: {{ n }}`` substitute to
    valid YAML before the loader sees them.
    """
    path = PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(f"prompt template not found: {path}")
    raw = path.read_text(encoding="utf-8")
    fm_text, body = _split_raw_front_matter(raw)

    env = _env()
    rendered_fm = env.from_string(fm_text).render(**variables) if fm_text else ""
    meta = yaml.safe_load(rendered_fm) or {}
    if not isinstance(meta, dict):
        raise ValueError(f"template {name}: front-matter must be a YAML mapping")
    if "system" not in meta:
        raise ValueError(f"template {name} missing 'system' in front-matter")
    if "tool" not in meta:
        raise ValueError(f"template {name} missing 'tool' in front-matter")

    rendered_user = env.from_string(body).render(**variables)

    return PromptCall(
        name=name,
        model=str(meta.get("model", os.environ.get("CLAUDE_MODEL", "anthropic/claude-sonnet-4-6"))),
        temperature=float(meta.get("temperature", 0.7)),
        max_tokens=int(meta.get("max_tokens", 1024)),
        system=str(meta["system"]),
        user=rendered_user,
        tool=meta["tool"],
    )


def run_template(
    name: str, variables: dict, *, spend_kind: str | None = None
) -> tuple[dict, PromptCall]:
    """Render + call `structured_generate`. Returns `(tool_input, PromptCall)`.

    Returning the `PromptCall` alongside the result lets callers compute
    prompt-version hashes (or anything else that depends on the rendered
    template) without re-rendering. Older call sites only used the dict
    return; those should switch to `result, call = run_template(...)`
    or `result = run_template(...)[0]`.

    `spend_kind` lets the caller tag the spend bucket for the daily-spend
    ceiling. Defaults to a per-template name (``claude_<name>``).
    """
    call = render_template(name, variables)
    log.debug(
        "prompt %s rendered: model=%s tokens=%d temp=%.2f",
        call.name, call.model, call.max_tokens, call.temperature,
    )
    kind = spend_kind or f"claude_{name.replace('-', '_')}"
    result = structured_generate(
        system=call.system,
        user=call.user,
        tool=call.tool,
        model=call.model,
        max_tokens=call.max_tokens,
        temperature=call.temperature,
        spend_kind=kind,
    )
    return result, call
