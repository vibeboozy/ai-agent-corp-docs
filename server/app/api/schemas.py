"""
ANCHOR: app.api.schemas
PURPOSE: Pydantic v2 request/response DTOs aligned with CLIENT_INFO.md (skeleton shapes).
Dependencies: domain enums/models (conceptually); no FastAPI imports beyond typing
DO:
- Keep shapes in sync with CLIENT_INFO.md
- Return citations on message_kind=answer (later)
DONT:
- Embed business logic in DTOs
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

AppealStatus = Literal[
    "open",
    "clarifying",
    "answered",
    "escalated",
    "resolved_by_officer",
    "closed",
]
MessageRole = Literal["user", "assistant", "officer", "system"]
MessageKind = Literal[
    "question",
    "clarification",
    "answer",
    "refusal",
    "escalation_notice",
    "canonical_answer",
]


class Citation(BaseModel):
    document_id: str
    chunk_id: str
    quote: str
    score: float | None = None
    document_title: str | None = None
    locator: str | None = None


class Appeal(BaseModel):
    id: UUID
    status: AppealStatus
    created_at: datetime
    updated_at: datetime
    user_id: str | None = None
    user_label: str | None = None
    topic: str | None = None
    summary: str | None = None
    escalation_id: UUID | None = None
    message_count: int = 0


class Message(BaseModel):
    id: UUID
    appeal_id: UUID
    role: MessageRole
    message_kind: MessageKind
    content: str
    created_at: datetime
    citations: list[Citation] = Field(default_factory=list)


class CreateAppealRequest(BaseModel):
    user_id: str | None = None
    user_label: str | None = None
    content: str | None = None


class CreateMessageRequest(BaseModel):
    content: str
    role: MessageRole = "user"


class OfficerReplyRequest(BaseModel):
    content: str


class ErrorBody(BaseModel):
    detail: Any
    code: str


class StatsResponse(BaseModel):
    """Aggregate stats placeholder — populated in later phases from persistence."""

    total_appeals: int = 0
    answered: int = 0
    escalated: int = 0
    clarifying: int = 0
