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
    specificity: str  # underspecified | ambiguous | specific | off_topic
    raw_specificity: str  # classifier label before prefer_specific_label
    candidates: list[dict[str, Any]]
    grounded: bool
    draft_answer: str
    citations: list[dict[str, Any]]
    clarification_text: str
    clarify_reason: str  # underspecified | ambiguous | max_clarify_exceeded
    escalation_reason: str
    outcome: str  # clarify | answer | escalate | refuse
    node_trace: list[str]
    quality_email: str
    # Observability for audit_events.payload
    latency_ms: dict[str, float]
    rerank_mode: str
    rerank_scores: list[dict[str, Any]]
