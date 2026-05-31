"""One-shot generator: translate the en→ko TOPIC_SEEDS into en→es.

Reads `app.vocab.seeds.TOPIC_SEEDS` (the canonical en→ko corpus),
calls Claude through the analysis service's `structured_generate`
helper to produce a Spanish translation for each English term, and
writes the result as `EN_ES_TOPIC_SEEDS` back into
`app/vocab/seeds.py` (preserving the rest of the file).

Run **once** during the rollout:

    docker compose exec gateway python -m scripts.seed_es_vocab

The script is idempotent on re-run because it generates the same
output (temperature 0). It is safe to commit the resulting
`seeds.py` so future deployments don't re-spend the ~$0.18 in
OpenRouter cost.

Cost: ~180 calls × ~$0.001 each ≈ $0.18. Bounded under MAX_DAILY_USD
via the `claude_seed_es_vocab` spend bucket.
"""

from __future__ import annotations

import json
import logging
import os
import re
import textwrap
import time
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)


_SYSTEM = textwrap.dedent("""\
    You translate English domain-vocabulary terms to Spanish for an
    interpretation-training flashcard deck. The audience is military,
    diplomatic, intelligence, medical, and cyber professionals.

    Rules:
    - Return the canonical Spanish term used in the relevant
      professional register, NOT a literal word-for-word translation.
    - If the English term is a compound (e.g. "command and control"),
      use the standard Spanish multi-word equivalent ("mando y
      control").
    - If multiple Spanish equivalents exist, prefer the one used in
      official Spanish-language military doctrine or treaty texts.
    - Respond by calling the translate_term tool. The `spanish`
      argument is the Spanish term itself — no parentheses, no
      explanations. Lowercase unless a proper noun.
""")

_TRANSLATE_TOOL = {
    "type": "function",
    "function": {
        "name": "translate_term",
        "description": (
            "Emit a faithful Spanish translation for one English domain-"
            "vocabulary term, suitable for an interpretation-training "
            "flashcard."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "spanish": {
                    "type": "string",
                    "description": (
                        "The Spanish equivalent term. Prefer the canonical "
                        "domain vocabulary used by Spanish-language military / "
                        "diplomatic / intelligence professionals. No "
                        "definitions, just the term."
                    ),
                },
            },
            "required": ["spanish"],
        },
    },
}


def _openrouter_client() -> tuple[httpx.Client, str, str]:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set in the gateway container; "
            "the seed generator can't translate without it."
        )
    base = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    model = os.environ.get("CLAUDE_MODEL", "anthropic/claude-sonnet-4-6")
    client = httpx.Client(
        base_url=base,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=httpx.Timeout(60.0, connect=5.0),
    )
    return client, model, base


def _translate(client: httpx.Client, model: str, term: str, domain: str, register: str) -> str:
    """One Claude call via OpenRouter; returns the Spanish term."""
    body = {
        "model": model,
        "max_tokens": 64,
        "temperature": 0.0,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Domain: {domain}\nRegister: {register}\n\n"
                    f"Translate the English term to Spanish:\n\n{term}"
                ),
            },
        ],
        "tools": [_TRANSLATE_TOOL],
        "tool_choice": {"type": "function", "function": {"name": "translate_term"}},
    }
    r = client.post("/chat/completions", json=body)
    r.raise_for_status()
    payload = r.json()
    msg = payload["choices"][0]["message"]
    tool_calls = msg.get("tool_calls") or []
    if not tool_calls:
        raise RuntimeError(f"model returned no tool call for {term!r}: {msg!r}")
    raw = tool_calls[0]["function"]["arguments"]
    args = raw if isinstance(raw, dict) else json.loads(raw)
    spanish = (args.get("spanish") or "").strip()
    if not spanish:
        raise RuntimeError(f"empty translation for {term!r}")
    return spanish


def _build_en_es_seeds() -> dict[str, list[dict]]:
    from app.vocab.seeds import TOPIC_SEEDS

    client, model, base = _openrouter_client()
    log.info("[seed_es_vocab.openrouter] base=%s model=%s", base, model)

    out: dict[str, list[dict]] = {}
    total = sum(len(v) for v in TOPIC_SEEDS.values())
    done = 0
    t0 = time.monotonic()
    try:
        for domain, items in TOPIC_SEEDS.items():
            out[domain] = []
            for item in items:
                term = item["term"]
                try:
                    spanish = _translate(client, model, term, domain, item["register"])
                except Exception:
                    log.exception(
                        "[seed_es_vocab.failed] term=%r — leaving placeholder", term
                    )
                    # Fail soft: insert a placeholder that a reviewer
                    # can spot and fix by hand.
                    spanish = f"<TODO:{term}>"
                out[domain].append(
                    {
                        "term": term,
                        "definition": spanish,
                        "register": item["register"],
                    }
                )
                done += 1
                if done % 10 == 0:
                    elapsed = time.monotonic() - t0
                    log.info(
                        "[seed_es_vocab.progress] %d/%d (%.1fs elapsed)",
                        done,
                        total,
                        elapsed,
                    )
    finally:
        client.close()
    return out


_BLOCK_BEGIN = "EN_ES_TOPIC_SEEDS: dict[str, list[dict]] = {"
_BLOCK_END_MARKER = "# Filled by scripts/seed_es_vocab.py — see operator checklist in"


def _format_block(seeds: dict[str, list[dict]]) -> str:
    """Format the new EN_ES_TOPIC_SEEDS as a Python literal that
    matches the visual style of TOPIC_SEEDS in seeds.py."""
    lines: list[str] = ["EN_ES_TOPIC_SEEDS: dict[str, list[dict]] = {"]
    for domain, items in seeds.items():
        lines.append(f"    {json.dumps(domain)}: [")
        for item in items:
            term = json.dumps(item["term"], ensure_ascii=False)
            defn = json.dumps(item["definition"], ensure_ascii=False)
            reg = json.dumps(item["register"], ensure_ascii=False)
            lines.append(
                f"        {{\"term\": {term}, \"definition\": {defn}, \"register\": {reg}}},"
            )
        lines.append("    ],")
    lines.append("}")
    return "\n".join(lines)


def _splice_into_seeds_file(formatted: str) -> Path:
    """Replace the placeholder EN_ES_TOPIC_SEEDS dict in seeds.py with
    the freshly-generated literal.

    Always writes the standalone formatted block to
    `/tmp/EN_ES_TOPIC_SEEDS.py` first, so a read-only-mount run
    isn't a total loss — the 3 minutes of Claude calls survive as a
    recoverable artifact that the operator can `docker cp` out.

    Then attempts to splice into the live seeds.py. On read-only or
    not-found, logs a clear pointer to the standalone artifact.
    """
    standalone = Path("/tmp/EN_ES_TOPIC_SEEDS.py")
    standalone.write_text(formatted + "\n", encoding="utf-8")
    log.info("[seed_es_vocab.standalone] formatted block at %s", standalone)

    candidates = [
        Path("/app/app/vocab/seeds.py"),
        Path(__file__).resolve().parent.parent / "app" / "vocab" / "seeds.py",
    ]
    target = next((p for p in candidates if p.exists()), None)
    if target is None:
        log.warning(
            "[seed_es_vocab.no_target] seeds.py not found in container; "
            "use standalone artifact at %s",
            standalone,
        )
        return standalone

    try:
        src = target.read_text(encoding="utf-8")
        pattern = re.compile(
            r"^EN_ES_TOPIC_SEEDS:\s*dict\[str,\s*list\[dict\]\]\s*=\s*\{.*?^\}",
            re.DOTALL | re.MULTILINE,
        )
        if not pattern.search(src):
            log.warning(
                "[seed_es_vocab.no_anchor] EN_ES_TOPIC_SEEDS placeholder not "
                "found in %s; use standalone artifact at %s",
                target,
                standalone,
            )
            return standalone
        new_src = pattern.sub(formatted, src, count=1)
        target.write_text(new_src, encoding="utf-8")
        return target
    except OSError as exc:
        log.warning(
            "[seed_es_vocab.readonly] %s is not writable (%s); use standalone "
            "artifact at %s — docker cp out and splice into host seeds.py",
            target,
            exc,
            standalone,
        )
        return standalone


def main() -> None:
    log.info("[seed_es_vocab.begin]")
    seeds = _build_en_es_seeds()
    log.info("[seed_es_vocab.generated] domains=%d", len(seeds))
    formatted = _format_block(seeds)
    target = _splice_into_seeds_file(formatted)
    log.info("[seed_es_vocab.done] wrote %s", target)


if __name__ == "__main__":
    main()
