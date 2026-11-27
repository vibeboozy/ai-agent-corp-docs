"""
ANCHOR: app.adapters.persistence.port
PURPOSE: Persistence / repository Protocol for appeals, messages, escalations, audit, stats.
Dependencies: domain models
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from app.domain.enums import AppealStatus, EscalationStatus, MessageKind, MessageRole
from app.domain.models import Appeal, Escalation, Message


@runtime_checkable
class Persistence(Protocol):
    async def ping(self) -> bool:
        """Health check against the store."""
        ...

    async def create_appeal(
        self,
        *,
        user_id: str | None = None,
        user_label: str | None = None,
        topic: str | None = None,
        status: AppealStatus = AppealStatus.OPEN,
    ) -> Appeal: ...

    async def get_appeal(self, appeal_id: UUID) -> Appeal | None: ...

    async def list_appeals(
        self,
        *,
        status: AppealStatus | None = None,
        user_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> tuple[list[Appeal], int]: ...

    async def update_appeal(
        self,
        appeal_id: UUID,
        *,
        status: AppealStatus | None = None,
        topic: str | None = None,
        summary: str | None = None,
        escalation_id: UUID | None = None,
    ) -> Appeal: ...

    async def add_message(
        self,
        *,
        appeal_id: UUID,
        role: MessageRole,
        message_kind: MessageKind,
        content: str,
        citations: list[dict[str, Any]] | None = None,
    ) -> Message: ...

    async def list_messages(
        self,
        appeal_id: UUID,
        *,
        after_id: UUID | None = None,
        limit: int = 100,
    ) -> list[Message]: ...

    async def count_messages(self, appeal_id: UUID) -> int: ...

    async def first_user_messages(
        self, appeal_ids: list[UUID]
    ) -> dict[UUID, str]:
        """Earliest user-role message content per appeal id (batch for list DTOs)."""
        ...

    async def create_escalation(
        self,
        *,
        appeal_id: UUID,
        reason: str,
        channel: str = "email",
        status: EscalationStatus = EscalationStatus.PENDING,
    ) -> Escalation: ...

    async def get_escalation(self, escalation_id: UUID) -> Escalation | None: ...

    async def update_escalation(
        self,
        escalation_id: UUID,
        *,
        status: EscalationStatus | None = None,
        quality_notified_at: datetime | None = None,
        officer_reply_at: datetime | None = None,
    ) -> Escalation: ...

    async def add_audit_event(
        self,
        *,
        appeal_id: UUID | None,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None: ...

    async def increment_learning_updates(self) -> None: ...

    async def get_stats(
        self,
        *,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> dict[str, Any]: ...
