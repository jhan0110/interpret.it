"""Reference translation generator using Claude Sonnet with tool_use structured output."""

from __future__ import annotations

import logging
import time
from typing import Literal

from pydantic import BaseModel

from ..llm.client import structured_generate

log = logging.getLogger(__name__)


class ReferenceBundle(BaseModel):
    canonical: str
    paraphrases: list[str]  # 3–5 acceptable alternatives


_REFERENCE_TOOL = {
    "name": "emit_reference",
    "description": "Emit the canonical reference translation and acceptable paraphrases.",
    "input_schema": {
        "type": "object",
        "properties": {
            "canonical_translation": {
                "type": "string",
                "description": "The single best translation of the source text, strictly matching the register and domain.",
            },
            "acceptable_paraphrases": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 3,
                "maxItems": 5,
                "description": "3 to 5 alternative translations that are semantically acceptable for the given register/domain.",
            },
        },
        "required": ["canonical_translation", "acceptable_paraphrases"],
    },
}

_SYSTEM_PROMPT = """\
You are a professional interpretation trainer specializing in {source_lang}→{target_lang} interpretation.
Your task is to produce a canonical reference translation and 3–5 acceptable paraphrases
for a given source text, strictly constrained by register and domain.

Register: {register}
Domain: {domain}

Rules:
- The canonical translation must be in the target language.
- It must precisely match the register: formal-military uses command structure and official terminology;
  formal-diplomatic uses diplomatic phrasing; informal uses natural conversational language.
- Paraphrases must be semantically equivalent but may use different lexical choices or phrasing.
- Preserve all temporal markers, quantities, and named entities exactly.
- Do not add or omit information.
- Respond only by calling the emit_reference tool.
"""


def generate_reference(
    source_text: str,
    source_lang: Literal["ko", "en"],
    target_lang: Literal["ko", "en"],
    register: Literal["formal-military", "formal-diplomatic", "informal"],
    domain: str,
) -> ReferenceBundle:
    """Generate canonical reference translation and acceptable paraphrases via Claude.

    Uses tool_use to enforce structured output — the model MUST call emit_reference.
    """
    t0 = time.monotonic()
    log.info(
        "[reference.begin] segment_text_len=%d source_lang=%s target_lang=%s",
        len(source_text),
        source_lang,
        target_lang,
    )

    system = _SYSTEM_PROMPT.format(
        source_lang=source_lang,
        target_lang=target_lang,
        register=register,
        domain=domain,
    )

    log.info("[reference.claude.begin] source_lang=%s target_lang=%s", source_lang, target_lang)
    t_claude = time.monotonic()
    inp = structured_generate(
        system=system,
        user=f"Source text ({source_lang}):\n\n{source_text}",
        tool=_REFERENCE_TOOL,
        spend_kind="claude_reference",
    )
    claude_ms = int((time.monotonic() - t_claude) * 1000)
    log.info("[reference.claude.done] took=%dms", claude_ms)

    bundle = ReferenceBundle(
        canonical=inp["canonical_translation"],
        paraphrases=inp["acceptable_paraphrases"],
    )
    total_ms = int((time.monotonic() - t0) * 1000)
    log.info(
        "[reference.done] canonical_len=%d paraphrases=%d total_took=%dms",
        len(bundle.canonical),
        len(bundle.paraphrases),
        total_ms,
    )
    return bundle
