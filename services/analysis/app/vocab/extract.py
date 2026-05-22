"""Arq job: extract missed vocabulary from a failed interpretation attempt."""

from __future__ import annotations

import logging

from app.llm.client import structured_generate
from app.rpc.gateway_client import push_vocab_extraction

log = logging.getLogger(__name__)

_EXTRACT_TOOL = {
    "name": "emit_vocab_extraction",
    "description": "Emit the list of vocabulary terms the learner missed or mis-rendered.",
    "input_schema": {
        "type": "object",
        "properties": {
            "missed_terms": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "term": {"type": "string", "description": "The term in source_lang"},
                        "gloss": {"type": "string", "description": "Correct rendering in target_lang"},
                        "register": {"type": "string", "enum": ["formal-military", "formal-diplomatic", "informal"]},
                        "gap_type": {"type": "string", "enum": ["knowledge_gap", "memory_gap"]},
                        "severity": {"type": "string", "enum": ["minor", "moderate", "critical"]},
                        "explanation": {"type": "string"},
                    },
                    "required": ["term", "gloss", "register", "gap_type", "severity", "explanation"],
                },
            }
        },
        "required": ["missed_terms"],
    },
}

_SYSTEM = """\
You are a pedagogy assistant for military/diplomatic interpreter training.
Given a source text, the learner's transcript, and a list of semantic errors,
identify vocabulary terms that the learner failed to produce correctly.

Classification rules:
- knowledge_gap: A domain-specialist term that requires training to know.
  The learner either omitted it entirely, used a generic substitute, or
  produced a clearly wrong translation. The term would appear in a domain
  glossary for trained interpreters.
- memory_gap: A high-frequency term in this domain that a trained interpreter
  should recall by rote. The learner likely dropped it under time pressure
  rather than not knowing it (e.g. common acronyms, basic domain nouns).

Only include terms with genuine pedagogical value. Skip:
- Function words, pronouns, common articles
- Terms the learner produced correctly
- Terms where the error was purely register or tense, not vocabulary knowledge

Emit at most 5 terms per call. Prefer critical > moderate > minor severity.
"""


async def run_vocab_extraction(_ctx: dict, payload: dict) -> None:
    """Arq job: call Claude to extract missed vocabulary, push to gateway."""
    attempt_id = payload["attempt_id"]
    learner_id = payload["learner_id"]
    domain = payload["domain"]
    source_lang = payload["source_lang"]
    target_lang = payload["target_lang"]

    user_msg = f"""\
Domain: {domain}
Direction: {source_lang} → {target_lang}
Register: {payload.get("register", "formal-military")}

Source text:
{payload["source_text"]}

Learner's transcript:
{payload["transcript"]}

Semantic errors identified:
{payload["errors"]}

Overall score: {payload["overall_score"]:.2f}
"""

    try:
        result = structured_generate(
            system=_SYSTEM,
            user=user_msg,
            tool=_EXTRACT_TOOL,
            max_tokens=512,
        )
    except Exception:
        log.exception("vocab extraction Claude call failed attempt=%s", attempt_id)
        return

    missed_terms = result.get("missed_terms", [])
    if not missed_terms:
        return

    await push_vocab_extraction(
        {
            "attempt_id": attempt_id,
            "learner_id": learner_id,
            "domain": domain,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "missed_terms": missed_terms,
        }
    )
    log.info(
        "vocab extraction complete attempt=%s terms=%d", attempt_id, len(missed_terms)
    )
