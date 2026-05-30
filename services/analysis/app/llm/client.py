"""Central LLM wrapper.

Uses the OpenAI SDK pointed at OpenRouter so Claude (and any other
chat-completion model on OpenRouter) is reachable through one key.

Call sites still pass Anthropic-style tool schemas
(``{"name", "description", "input_schema"}``) — this wrapper translates
to OpenAI function-calling format internally so no downstream module
needs to know which provider it talks to.
"""

from __future__ import annotations

import json
import os

from openai import OpenAI

_client: OpenAI | None = None

_DEFAULT_MODEL = "anthropic/claude-sonnet-4-6"
_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is required (or OPENAI_API_KEY as fallback)"
            )
        import httpx

        # OpenRouter occasionally stalls on first-token latency. The
        # SDK default timeout is 600s, which would hog the entire
        # 300s generation budget on a single bad request. Use a
        # 5s connect + 60s read budget and let the SDK retry twice.
        timeout = httpx.Timeout(60.0, connect=5.0)
        _client = OpenAI(
            api_key=api_key,
            base_url=os.environ.get("OPENROUTER_BASE_URL", _DEFAULT_BASE_URL),
            timeout=timeout,
            max_retries=2,
        )
    return _client


def _anthropic_tool_to_openai(tool: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool["input_schema"],
        },
    }


def structured_generate(
    *,
    system: str,
    user: str,
    tool: dict,
    model: str | None = None,
    max_tokens: int = 1024,
    temperature: float | None = None,
    spend_kind: str = "claude_eval",
) -> dict:
    """Call the LLM with a single tool and return the tool input dict.

    Parameters
    ----------
    system : str
        System prompt.
    user : str
        User-turn message.
    tool : dict
        Anthropic-style tool schema with ``name``, ``description``, and
        ``input_schema``. Translated to OpenAI function format on the
        wire. The model is forced to call exactly this tool.
    model : str | None
        Override the model. Defaults to the ``CLAUDE_MODEL`` env var
        (must be an OpenRouter-qualified path like
        ``anthropic/claude-sonnet-4-6``), falling back to the constant
        above.
    max_tokens : int
        Maximum tokens in the response.

    Returns
    -------
    dict
        The parsed ``arguments`` dict from the tool call.

    Raises
    ------
    RuntimeError
        If the response contains no tool call.
    """
    resolved_model = model or os.environ.get("CLAUDE_MODEL", _DEFAULT_MODEL)
    client = _get_client()

    fn_tool = _anthropic_tool_to_openai(tool)
    fn_name = fn_tool["function"]["name"]

    from app.spend import record_spend

    record_spend(spend_kind)

    create_kwargs: dict = {
        "model": resolved_model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "tools": [fn_tool],
        "tool_choice": {"type": "function", "function": {"name": fn_name}},
    }
    if temperature is not None:
        create_kwargs["temperature"] = temperature
    response = client.chat.completions.create(**create_kwargs)

    message = response.choices[0].message
    tool_calls = message.tool_calls or []
    if not tool_calls:
        raise RuntimeError(
            f"Model did not call tool '{fn_name}'. "
            f"Finish reason: {response.choices[0].finish_reason}"
        )

    raw_args = tool_calls[0].function.arguments
    if isinstance(raw_args, dict):
        return raw_args
    return json.loads(raw_args)
