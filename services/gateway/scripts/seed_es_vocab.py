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
import re
import sys
import textwrap
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)


# The generator runs inside the gateway container but reuses the
# analysis service's LLM client. The container has both packages on
# sys.path because we bind-mount sources and PYTHONPATH covers both.
def _import_llm_client():
    try:
        from app.llm.client import structured_generate  # type: ignore[import]

        return structured_generate
    except ImportError:
        pass
    # Fall back to importing from the analysis path explicitly.
    analysis_root = Path("/app").parent / "analysis" / "app"
    if analysis_root.exists():
        sys.path.insert(0, str(analysis_root.parent))
    from analysis.app.llm.client import structured_generate  # type: ignore[import]

    return structured_generate


_TRANSLATE_TOOL = {
    "name": "translate_term",
    "description": (
        "Emit a faithful Spanish translation for one English domain-vocabulary "
        "term, suitable for an interpretation-training flashcard."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "spanish": {
                "type": "string",
                "description": (
                    "The Spanish equivalent term. Prefer the canonical domain "
                    "vocabulary used by Spanish-language military / diplomatic / "
                    "intelligence professionals. No definitions, just the term."
                ),
            },
        },
        "required": ["spanish"],
    },
}

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
    - Output only the Spanish term itself. No parentheses, no
      explanations. Lowercase unless a proper noun.
""")


def _translate(term: str, domain: str, register: str, structured_generate) -> str:
    inp = structured_generate(
        system=_SYSTEM,
        user=(
            f"Domain: {domain}\nRegister: {register}\n\n"
            f"Translate the English term to Spanish:\n\n{term}"
        ),
        tool=_TRANSLATE_TOOL,
        spend_kind="claude_seed_es_vocab",
        temperature=0.0,
        max_tokens=64,
    )
    spanish = (inp.get("spanish") or "").strip()
    if not spanish:
        raise RuntimeError(f"empty translation for {term!r}")
    return spanish


def _build_en_es_seeds(structured_generate) -> dict[str, list[dict]]:
    from app.vocab.seeds import TOPIC_SEEDS

    out: dict[str, list[dict]] = {}
    total = sum(len(v) for v in TOPIC_SEEDS.values())
    done = 0
    t0 = time.monotonic()
    for domain, items in TOPIC_SEEDS.items():
        out[domain] = []
        for item in items:
            term = item["term"]
            try:
                spanish = _translate(term, domain, item["register"], structured_generate)
            except Exception:
                log.exception("[seed_es_vocab.failed] term=%r — leaving placeholder", term)
                # Fail soft: insert a placeholder that's obviously
                # a fallback so a reviewer can fix it by hand.
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
    the freshly-generated literal. Returns the path written."""
    # When running inside the gateway container the source is at /app
    # via the bind mount; on host the path is the repo location.
    candidates = [
        Path("/app/app/vocab/seeds.py"),
        Path(__file__).resolve().parent.parent / "app" / "vocab" / "seeds.py",
    ]
    target = next((p for p in candidates if p.exists()), None)
    if target is None:
        raise FileNotFoundError("could not locate seeds.py")

    src = target.read_text(encoding="utf-8")
    # Match the existing block: the line starting with
    # EN_ES_TOPIC_SEEDS: dict[str, list[dict]] = { up to the matching
    # closing brace at column 0.
    pattern = re.compile(
        r"^EN_ES_TOPIC_SEEDS:\s*dict\[str,\s*list\[dict\]\]\s*=\s*\{.*?^\}",
        re.DOTALL | re.MULTILINE,
    )
    if not pattern.search(src):
        raise RuntimeError("could not find EN_ES_TOPIC_SEEDS block in seeds.py")
    new_src = pattern.sub(formatted, src, count=1)
    target.write_text(new_src, encoding="utf-8")
    return target


def main() -> None:
    structured_generate = _import_llm_client()
    log.info("[seed_es_vocab.begin]")
    seeds = _build_en_es_seeds(structured_generate)
    log.info("[seed_es_vocab.generated] domains=%d", len(seeds))
    formatted = _format_block(seeds)
    target = _splice_into_seeds_file(formatted)
    log.info("[seed_es_vocab.done] wrote %s", target)


if __name__ == "__main__":
    main()
