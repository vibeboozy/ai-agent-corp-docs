"""
ANCHOR: app.application.dialogue.state
PURPOSE: Typed LangGraph state for appeal dialogue turns.
Dependencies: domain models (appeal_id, messages, candidates)
DO:
- Keep state serializable for optional checkpointing by appeal_id
DONT:
- Store secrets or unnecessary PII in graph state
"""

from __future__ import annotations

from typing import Any, TypedDict


class DialogueState(TypedDict, total=False):
    """Graph state passed between dialogue nodes."""

    appeal_id: str
    user_message: str
    history: list[str]
    clarify_turns: int
    max_clarify_turns: int
    specificity: str  # underspecified | ambiguous | specific
    candidates: list[dict[str, Any]]
    grounded: bool
    draft_answer: str
    citations: list[dict[str, Any]]
    clarification_text: str
    escalation_reason: str
    outcome: str  # clarify | answer | escalate
    node_trace: list[str]
    quality_email: str
