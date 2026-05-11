"""Central Anthropic SDK wrapper.

All modules that need structured LLM output should call ``structured_generate``
rather than instantiating ``anthropic.Anthropic`` directly.  This keeps SDK
version bumps and provider swaps in one place.
"""

from __future__ import annotations

import os

import anthropic

_client: anthropic.Anthropic | None = None

_DEFAULT_MODEL = "claude-sonnet-4-6"


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def structured_generate(
    *,
    system: str,
    user: str,
    tool: dict,
    model: str | None = None,
    max_tokens: int = 1024,
) -> dict:
    """Call Claude with a single tool and return the tool_use input dict.

    Parameters
    ----------
    system:
        The system prompt string.
    user:
        The user-turn message string.
    tool:
        A tool schema dict with keys ``name``, ``description``, and
        ``input_schema``.  The model is forced to call this tool via
        ``tool_choice={"type": "any"}``.
    model:
        Override the Claude model name.  Defaults to the ``CLAUDE_MODEL``
        environment variable, falling back to ``"claude-sonnet-4-6"``.
    max_tokens:
        Maximum tokens in the response (default 1024).

    Returns
    -------
    dict
        The ``input`` dict from the first ``tool_use`` block in the response.

    Raises
    ------
    RuntimeError
        If the response contains no ``tool_use`` block.
    """
    resolved_model = model or os.environ.get("CLAUDE_MODEL", _DEFAULT_MODEL)
    client = _get_client()

    response = client.messages.create(
        model=resolved_model,
        max_tokens=max_tokens,
        system=system,
        tools=[tool],
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": user}],
    )

    for block in response.content:
        if block.type == "tool_use":
            return block.input  # type: ignore[return-value]

    raise RuntimeError(
        f"Claude did not call tool '{tool.get('name', '?')}'. "
        f"Stop reason: {response.stop_reason}"
    )
