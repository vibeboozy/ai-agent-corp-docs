"""
ANCHOR: app.domain.enums
PURPOSE: Domain enumerations for appeal status, roles, message kinds.
Dependencies: stdlib enum
"""

from __future__ import annotations

from enum import StrEnum


class AppealStatus(StrEnum):
    OPEN = "open"
    CLARIFYING = "clarifying"
    ANSWERED = "answered"
    ESCALATED = "escalated"
    RESOLVED_BY_OFFICER = "resolved_by_officer"
    CLOSED = "closed"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    OFFICER = "officer"
    SYSTEM = "system"


class MessageKind(StrEnum):
    QUESTION = "question"
    CLARIFICATION = "clarification"
    ANSWER = "answer"
    REFUSAL = "refusal"
    ESCALATION_NOTICE = "escalation_notice"
    CANONICAL_ANSWER = "canonical_answer"


class EscalationStatus(StrEnum):
    PENDING = "pending"
    ANSWERED = "answered"
    CLOSED = "closed"
