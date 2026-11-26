"""
ANCHOR: app.domain.models
PURPOSE: Domain entity skeletons: Appeal, Message, Escalation, Document/Chunk, CanonicalAnswer.
Dependencies: app.domain.enums
DO:
- Citations required on grounded assistant answers (later enforcement)
DONT:
- Persist directly — use persistence port
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from app.domain.enums import AppealStatus, EscalationStatus, MessageKind, MessageRole


@dataclass
class ChunkCitation:
    document_id: str
    chunk_id: str
    quote: str
    score: float | None = None
    document_title: str | None = None
    locator: str | None = None


@dataclass
class Appeal:
    id: UUID
    status: AppealStatus
    created_at: datetime
    updated_at: datetime
    user_id: str | None = None
    user_label: str | None = None
    topic: str | None = None
    summary: str | None = None
    escalation_id: UUID | None = None


@dataclass
class Message:
    id: UUID
    appeal_id: UUID
    role: MessageRole
    message_kind: MessageKind
    content: str
    created_at: datetime
    citations: list[ChunkCitation] = field(default_factory=list)


@dataclass
class Escalation:
    id: UUID
    appeal_id: UUID
    reason: str
    status: EscalationStatus
    channel: str = "email"
    quality_notified_at: datetime | None = None
    officer_reply_at: datetime | None = None


@dataclass
class DocumentMeta:
    id: str
    source_path: str
    title: str
    version: str | None = None
    effective_date: datetime | None = None
    ingested_at: datetime | None = None
    checksum: str | None = None


@dataclass
class ChunkMeta:
    id: str
    document_id: str
    text: str
    token_count: int | None = None
    page: str | None = None
    section: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
