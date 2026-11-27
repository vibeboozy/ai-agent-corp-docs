"""
ANCHOR: app.api.mapping
PURPOSE: Map domain entities to CLIENT_INFO response DTOs.
Dependencies: app.domain.models, app.api.schemas
"""

from __future__ import annotations

from app.api import schemas
from app.domain.models import Appeal, Message


def to_appeal_dto(
    appeal: Appeal,
    *,
    message_count: int = 0,
    question: str | None = None,
) -> schemas.Appeal:
    # Prefer explicit first-user-message question; fall back to topic for empty chats.
    resolved_question = question if (question and question.strip()) else appeal.topic
    return schemas.Appeal(
        id=appeal.id,
        status=appeal.status.value,  # type: ignore[arg-type]
        created_at=appeal.created_at,
        updated_at=appeal.updated_at,
        user_id=appeal.user_id,
        user_label=appeal.user_label,
        topic=appeal.topic,
        summary=appeal.summary,
        question=resolved_question,
        escalation_id=appeal.escalation_id,
        message_count=message_count,
    )


def to_message_dto(message: Message) -> schemas.Message:
    return schemas.Message(
        id=message.id,
        appeal_id=message.appeal_id,
        role=message.role.value,  # type: ignore[arg-type]
        message_kind=message.message_kind.value,  # type: ignore[arg-type]
        content=message.content,
        created_at=message.created_at,
        citations=[
            schemas.Citation(
                document_id=c.document_id,
                chunk_id=c.chunk_id,
                quote=c.quote,
                score=c.score,
                document_title=c.document_title,
                locator=c.locator,
            )
            for c in message.citations
        ],
    )
