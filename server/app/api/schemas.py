"""
ANCHOR: app.api.schemas
PURPOSE: Pydantic v2 request/response DTOs aligned with CLIENT_INFO.md.
Dependencies: domain enums/models (conceptually); no FastAPI imports beyond typing
DO:
- Keep shapes in sync with CLIENT_INFO.md
- Return citations on message_kind=answer
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
    # First user message content (for quality-cabinet list labels without a second fetch).
    question: str | None = None
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


class FirstMessage(BaseModel):
    content: str


class CreateAppealRequest(BaseModel):
    user_id: str | None = None
    user_label: str | None = None
    topic: str | None = None
    message: FirstMessage | None = None


class CreateAppealResponse(BaseModel):
    appeal: Appeal
    messages: list[Message] = Field(default_factory=list)


class CreateMessageRequest(BaseModel):
    content: str
    role: MessageRole = "user"


class CreateMessageResponse(BaseModel):
    appeal: Appeal
    messages: list[Message]


class OfficerReplyRequest(BaseModel):
    content: str
    source_document_hint: str | None = None


class LearningInfo(BaseModel):
    accepted: bool
    ingest_job_id: str | None = None
    escalation_id: UUID | None = None


class OfficerReplyResponse(BaseModel):
    appeal: Appeal
    message: Message
    learning: LearningInfo


class AppealListResponse(BaseModel):
    items: list[Appeal]
    total: int
    limit: int
    offset: int


class MessageListResponse(BaseModel):
    appeal_id: UUID
    items: list[Message]


class ErrorBody(BaseModel):
    detail: Any
    code: str


class StatsWindow(BaseModel):
    from_: str | None = Field(default=None, alias="from")
    to: str | None = None

    model_config = {"populate_by_name": True}


class StatsResponse(BaseModel):
    appeals_total: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)
    messages_total: int = 0
    clarify_rate: float = 0.0
    escalation_rate: float = 0.0
    answered_rate: float = 0.0
    learning_updates: int = 0
    window: StatsWindow = Field(default_factory=StatsWindow)
