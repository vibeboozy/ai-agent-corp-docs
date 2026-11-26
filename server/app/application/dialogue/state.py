"""
ANCHOR: app.application.dialogue.state
PURPOSE: Typed LangGraph state placeholder for appeal dialogue turns.
Dependencies: domain models (appeal_id, messages, candidates)
DO:
- Keep state serializable for optional checkpointing by appeal_id
DONT:
- Store secrets or unnecessary PII in graph state
"""

from __future__ import annotations

from typing import Any, TypedDict


class DialogueState(TypedDict, total=False):
    """Skeleton graph state — fields filled in later phases."""

    appeal_id: str
    user_message: str
    clarify_turns: int
    candidates: list[dict[str, Any]]
    draft_answer: str
    citations: list[dict[str, Any]]
    outcome: str  # clarify | answer | escalate
