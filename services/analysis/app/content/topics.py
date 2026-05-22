"""Canonical topic list for content generation.

Source-of-truth for the dashboard multi-select. Keep in sync with
`CLAUDE.md` Content-generation-parameters section.
"""

from __future__ import annotations

from typing import Literal

Topic = Literal[
    "logistics",
    "diplomacy",
    "intelligence",
    "operations",
    "medical",
    "cyber",
]

TOPICS: tuple[Topic, ...] = (
    "logistics",
    "diplomacy",
    "intelligence",
    "operations",
    "medical",
    "cyber",
)

TOPIC_DESCRIPTIONS: dict[Topic, str] = {
    "logistics": "supply, transport, sustainment, and movement of personnel and materiel",
    "diplomacy": "interstate relations, negotiations, joint statements, and protocol",
    "intelligence": "briefings, threat assessments, signals analysis, and indicators",
    "operations": "tactical planning, mission coordination, and orders",
    "medical": "combat medicine, MEDEVAC, casualty triage, and field care",
    "cyber": "information warfare, network defense, and incident response",
}
