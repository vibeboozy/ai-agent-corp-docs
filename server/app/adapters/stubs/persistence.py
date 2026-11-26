"""
ANCHOR: app.adapters.stubs.persistence
PURPOSE: StubPersistence — in-memory store for unit tests (not durable).
Dependencies: app.adapters.persistence.port.Persistence; domain models
DO:
- Use for unit tests and default CI
DONT:
- Use as demo durability across restarts
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.adapters.persistence.port import Persistence
from app.domain.enums import AppealStatus, EscalationStatus, MessageKind, MessageRole
from app.domain.errors import ConflictError, NotFoundError
from app.domain.models import Appeal, ChunkCitation, Escalation, Message


def _utcnow() -> datetime:
    return datetime.now(UTC)


class StubPersistence:
    """In-memory persistence implementing the Persistence port."""

    def __init__(self) -> None:
        self._appeals: dict[UUID, Appeal] = {}
        self._messages: dict[UUID, list[Message]] = {}
        self._escalations: dict[UUID, Escalation] = {}
        self._audit: list[dict[str, Any]] = []
        self._learning_updates: int = 0

    async def ping(self) -> bool:
        return True

    async def create_appeal(
        self,
        *,
        user_id: str | None = None,
        user_label: str | None = None,
        topic: str | None = None,
        status: AppealStatus = AppealStatus.OPEN,
    ) -> Appeal:
        now = _utcnow()
        appeal = Appeal(
            id=uuid4(),
            status=status,
            created_at=now,
            updated_at=now,
            user_id=user_id,
            user_label=user_label,
            topic=topic,
        )
        self._appeals[appeal.id] = appeal
        self._messages[appeal.id] = []
        await self.add_audit_event(
            appeal_id=appeal.id,
            event_type="appeal_created",
            payload={"status": status.value},
        )
        return appeal

    async def get_appeal(self, appeal_id: UUID) -> Appeal | None:
        return self._appeals.get(appeal_id)

    async def list_appeals(
        self,
        *,
        status: AppealStatus | None = None,
        user_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> tuple[list[Appeal], int]:
        items = list(self._appeals.values())
        if status is not None:
            items = [a for a in items if a.status == status]
        if user_id is not None:
            items = [a for a in items if a.user_id == user_id]
        if created_from is not None:
            items = [a for a in items if a.created_at >= created_from]
        if created_to is not None:
            items = [a for a in items if a.created_at <= created_to]
        items.sort(key=lambda a: a.created_at, reverse=True)
        total = len(items)
        return items[offset : offset + limit], total

    async def update_appeal(
        self,
        appeal_id: UUID,
        *,
        status: AppealStatus | None = None,
        topic: str | None = None,
        summary: str | None = None,
        escalation_id: UUID | None = None,
    ) -> Appeal:
        appeal = self._appeals.get(appeal_id)
        if appeal is None:
            raise NotFoundError(f"Appeal {appeal_id} not found")
        if status is not None:
            appeal.status = status
        if topic is not None:
            appeal.topic = topic
        if summary is not None:
            appeal.summary = summary
        if escalation_id is not None:
            appeal.escalation_id = escalation_id
        appeal.updated_at = _utcnow()
        await self.add_audit_event(
            appeal_id=appeal_id,
            event_type="appeal_updated",
            payload={
                "status": appeal.status.value,
                "escalation_id": str(appeal.escalation_id) if appeal.escalation_id else None,
            },
        )
        return appeal

    async def add_message(
        self,
        *,
        appeal_id: UUID,
        role: MessageRole,
        message_kind: MessageKind,
        content: str,
        citations: list[dict[str, Any]] | None = None,
    ) -> Message:
        if appeal_id not in self._appeals:
            raise NotFoundError(f"Appeal {appeal_id} not found")
        cites = [
            ChunkCitation(
                document_id=c["document_id"],
                chunk_id=c["chunk_id"],
                quote=c["quote"],
                score=c.get("score"),
                document_title=c.get("document_title"),
                locator=c.get("locator"),
            )
            for c in (citations or [])
        ]
        msg = Message(
            id=uuid4(),
            appeal_id=appeal_id,
            role=role,
            message_kind=message_kind,
            content=content,
            created_at=_utcnow(),
            citations=cites,
        )
        self._messages[appeal_id].append(msg)
        appeal = self._appeals[appeal_id]
        appeal.updated_at = _utcnow()
        await self.add_audit_event(
            appeal_id=appeal_id,
            event_type="message_added",
            payload={
                "message_id": str(msg.id),
                "role": role.value,
                "message_kind": message_kind.value,
            },
        )
        return msg

    async def list_messages(
        self,
        appeal_id: UUID,
        *,
        after_id: UUID | None = None,
        limit: int = 100,
    ) -> list[Message]:
        if appeal_id not in self._appeals:
            raise NotFoundError(f"Appeal {appeal_id} not found")
        msgs = list(self._messages.get(appeal_id, []))
        if after_id is not None:
            idx = next((i for i, m in enumerate(msgs) if m.id == after_id), None)
            if idx is None:
                return []
            msgs = msgs[idx + 1 :]
        return msgs[:limit]

    async def count_messages(self, appeal_id: UUID) -> int:
        return len(self._messages.get(appeal_id, []))

    async def create_escalation(
        self,
        *,
        appeal_id: UUID,
        reason: str,
        channel: str = "email",
        status: EscalationStatus = EscalationStatus.PENDING,
    ) -> Escalation:
        if appeal_id not in self._appeals:
            raise NotFoundError(f"Appeal {appeal_id} not found")
        esc = Escalation(
            id=uuid4(),
            appeal_id=appeal_id,
            reason=reason,
            status=status,
            channel=channel,
            quality_notified_at=_utcnow(),
        )
        self._escalations[esc.id] = esc
        await self.add_audit_event(
            appeal_id=appeal_id,
            event_type="escalation_created",
            payload={"escalation_id": str(esc.id), "reason": reason},
        )
        return esc

    async def get_escalation(self, escalation_id: UUID) -> Escalation | None:
        return self._escalations.get(escalation_id)

    async def update_escalation(
        self,
        escalation_id: UUID,
        *,
        status: EscalationStatus | None = None,
        quality_notified_at: datetime | None = None,
        officer_reply_at: datetime | None = None,
    ) -> Escalation:
        esc = self._escalations.get(escalation_id)
        if esc is None:
            raise NotFoundError(f"Escalation {escalation_id} not found")
        if status is not None:
            esc.status = status
        if quality_notified_at is not None:
            esc.quality_notified_at = quality_notified_at
        if officer_reply_at is not None:
            esc.officer_reply_at = officer_reply_at
        await self.add_audit_event(
            appeal_id=esc.appeal_id,
            event_type="escalation_updated",
            payload={"escalation_id": str(escalation_id), "status": esc.status.value},
        )
        return esc

    async def add_audit_event(
        self,
        *,
        appeal_id: UUID | None,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self._audit.append(
            {
                "id": str(uuid4()),
                "appeal_id": str(appeal_id) if appeal_id else None,
                "event_type": event_type,
                "payload": payload or {},
                "created_at": _utcnow().isoformat(),
            }
        )

    async def increment_learning_updates(self) -> None:
        self._learning_updates += 1

    async def get_stats(
        self,
        *,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> dict[str, Any]:
        appeals = list(self._appeals.values())
        if created_from is not None:
            appeals = [a for a in appeals if a.created_at >= created_from]
        if created_to is not None:
            appeals = [a for a in appeals if a.created_at <= created_to]
        by_status = {s.value: 0 for s in AppealStatus}
        for a in appeals:
            by_status[a.status.value] += 1
        total = len(appeals) or 1
        messages_total = sum(len(self._messages.get(a.id, [])) for a in appeals)
        clarifying = by_status[AppealStatus.CLARIFYING.value]
        escalated = by_status[AppealStatus.ESCALATED.value]
        answered = by_status[AppealStatus.ANSWERED.value]
        return {
            "appeals_total": len(appeals),
            "by_status": by_status,
            "messages_total": messages_total,
            "clarify_rate": clarifying / total if appeals else 0.0,
            "escalation_rate": escalated / total if appeals else 0.0,
            "answered_rate": answered / total if appeals else 0.0,
            "learning_updates": self._learning_updates,
            "window": {
                "from": created_from.isoformat() if created_from else None,
                "to": created_to.isoformat() if created_to else None,
            },
        }

    # --- helpers for tests ---
    def audit_events(self) -> list[dict[str, Any]]:
        return list(self._audit)

    def require_open_for_message(self, appeal: Appeal) -> None:
        if appeal.status == AppealStatus.CLOSED:
            raise ConflictError("Appeal is closed")


_: Persistence = StubPersistence()  # type: ignore[assignment]
