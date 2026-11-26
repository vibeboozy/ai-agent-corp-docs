"""
ANCHOR: app.adapters.persistence.sqlalchemy.adapter
PURPOSE: SqlAlchemyPersistence for PostgreSQL (async + asyncpg).
Dependencies: sqlalchemy.ext.asyncio, asyncpg, Settings.DATABASE_URL
DO:
- Use alembic migrations in persistence phase
DONT:
- Drop durable history for convenience
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.adapters.persistence.port import Persistence
from app.adapters.persistence.sqlalchemy.models import (
    AppealRow,
    AuditEventRow,
    Base,
    EscalationRow,
    MessageRow,
    MetaCounterRow,
)
from app.domain.enums import AppealStatus, EscalationStatus, MessageKind, MessageRole
from app.domain.errors import NotFoundError
from app.domain.models import Appeal, ChunkCitation, Escalation, Message


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SqlAlchemyPersistence:
    """PostgreSQL persistence adapter implementing the Persistence port."""

    def __init__(
        self,
        *,
        database_url: str,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_timeout_s: float = 30.0,
        echo: bool = False,
    ) -> None:
        self._engine = create_async_engine(
            database_url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout_s,
            echo=echo,
        )
        self._sessionmaker = async_sessionmaker(self._engine, expire_on_commit=False)

    async def create_schema(self) -> None:
        """Dev helper — prefer Alembic in real deployments."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def ping(self) -> bool:
        async with self._sessionmaker() as session:
            await session.execute(select(1))
            return True

    async def create_appeal(
        self,
        *,
        user_id: str | None = None,
        user_label: str | None = None,
        topic: str | None = None,
        status: AppealStatus = AppealStatus.OPEN,
    ) -> Appeal:
        async with self._sessionmaker() as session:
            row = AppealRow(
                id=uuid4(),
                status=status.value,
                user_id=user_id,
                user_label=user_label,
                topic=topic,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
            session.add(row)
            await self._audit(session, appeal_id=row.id, event_type="appeal_created", payload={})
            await session.commit()
            await session.refresh(row)
            return self._to_appeal(row)

    async def get_appeal(self, appeal_id: UUID) -> Appeal | None:
        async with self._sessionmaker() as session:
            row = await session.get(AppealRow, appeal_id)
            return self._to_appeal(row) if row else None

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
        async with self._sessionmaker() as session:
            stmt = select(AppealRow)
            count_stmt = select(func.count()).select_from(AppealRow)
            if status is not None:
                stmt = stmt.where(AppealRow.status == status.value)
                count_stmt = count_stmt.where(AppealRow.status == status.value)
            if user_id is not None:
                stmt = stmt.where(AppealRow.user_id == user_id)
                count_stmt = count_stmt.where(AppealRow.user_id == user_id)
            if created_from is not None:
                stmt = stmt.where(AppealRow.created_at >= created_from)
                count_stmt = count_stmt.where(AppealRow.created_at >= created_from)
            if created_to is not None:
                stmt = stmt.where(AppealRow.created_at <= created_to)
                count_stmt = count_stmt.where(AppealRow.created_at <= created_to)
            total = int((await session.execute(count_stmt)).scalar_one())
            rows = (
                await session.execute(
                    stmt.order_by(AppealRow.created_at.desc()).offset(offset).limit(limit)
                )
            ).scalars().all()
            return [self._to_appeal(r) for r in rows], total

    async def update_appeal(
        self,
        appeal_id: UUID,
        *,
        status: AppealStatus | None = None,
        topic: str | None = None,
        summary: str | None = None,
        escalation_id: UUID | None = None,
    ) -> Appeal:
        async with self._sessionmaker() as session:
            row = await session.get(AppealRow, appeal_id)
            if row is None:
                raise NotFoundError(f"Appeal {appeal_id} not found")
            if status is not None:
                row.status = status.value
            if topic is not None:
                row.topic = topic
            if summary is not None:
                row.summary = summary
            if escalation_id is not None:
                row.escalation_id = escalation_id
            row.updated_at = _utcnow()
            await self._audit(
                session,
                appeal_id=appeal_id,
                event_type="appeal_updated",
                payload={"status": row.status},
            )
            await session.commit()
            await session.refresh(row)
            return self._to_appeal(row)

    async def add_message(
        self,
        *,
        appeal_id: UUID,
        role: MessageRole,
        message_kind: MessageKind,
        content: str,
        citations: list[dict[str, Any]] | None = None,
    ) -> Message:
        async with self._sessionmaker() as session:
            appeal = await session.get(AppealRow, appeal_id)
            if appeal is None:
                raise NotFoundError(f"Appeal {appeal_id} not found")
            row = MessageRow(
                id=uuid4(),
                appeal_id=appeal_id,
                role=role.value,
                message_kind=message_kind.value,
                content=content,
                created_at=_utcnow(),
                citations=citations or [],
            )
            session.add(row)
            appeal.updated_at = _utcnow()
            await self._audit(
                session,
                appeal_id=appeal_id,
                event_type="message_added",
                payload={"message_id": str(row.id), "role": role.value},
            )
            await session.commit()
            await session.refresh(row)
            return self._to_message(row)

    async def list_messages(
        self,
        appeal_id: UUID,
        *,
        after_id: UUID | None = None,
        limit: int = 100,
    ) -> list[Message]:
        async with self._sessionmaker() as session:
            appeal = await session.get(AppealRow, appeal_id)
            if appeal is None:
                raise NotFoundError(f"Appeal {appeal_id} not found")
            stmt = (
                select(MessageRow)
                .where(MessageRow.appeal_id == appeal_id)
                .order_by(MessageRow.created_at.asc())
            )
            rows = list((await session.execute(stmt)).scalars().all())
            if after_id is not None:
                idx = next((i for i, r in enumerate(rows) if r.id == after_id), None)
                rows = [] if idx is None else rows[idx + 1 :]
            return [self._to_message(r) for r in rows[:limit]]

    async def count_messages(self, appeal_id: UUID) -> int:
        async with self._sessionmaker() as session:
            stmt = select(func.count()).select_from(MessageRow).where(MessageRow.appeal_id == appeal_id)
            return int((await session.execute(stmt)).scalar_one())

    async def create_escalation(
        self,
        *,
        appeal_id: UUID,
        reason: str,
        channel: str = "email",
        status: EscalationStatus = EscalationStatus.PENDING,
    ) -> Escalation:
        async with self._sessionmaker() as session:
            row = EscalationRow(
                id=uuid4(),
                appeal_id=appeal_id,
                reason=reason,
                status=status.value,
                channel=channel,
                quality_notified_at=_utcnow(),
            )
            session.add(row)
            await self._audit(
                session,
                appeal_id=appeal_id,
                event_type="escalation_created",
                payload={"escalation_id": str(row.id)},
            )
            await session.commit()
            await session.refresh(row)
            return self._to_escalation(row)

    async def get_escalation(self, escalation_id: UUID) -> Escalation | None:
        async with self._sessionmaker() as session:
            row = await session.get(EscalationRow, escalation_id)
            return self._to_escalation(row) if row else None

    async def update_escalation(
        self,
        escalation_id: UUID,
        *,
        status: EscalationStatus | None = None,
        quality_notified_at: datetime | None = None,
        officer_reply_at: datetime | None = None,
    ) -> Escalation:
        async with self._sessionmaker() as session:
            row = await session.get(EscalationRow, escalation_id)
            if row is None:
                raise NotFoundError(f"Escalation {escalation_id} not found")
            if status is not None:
                row.status = status.value
            if quality_notified_at is not None:
                row.quality_notified_at = quality_notified_at
            if officer_reply_at is not None:
                row.officer_reply_at = officer_reply_at
            await session.commit()
            await session.refresh(row)
            return self._to_escalation(row)

    async def add_audit_event(
        self,
        *,
        appeal_id: UUID | None,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        async with self._sessionmaker() as session:
            await self._audit(session, appeal_id=appeal_id, event_type=event_type, payload=payload)
            await session.commit()

    async def increment_learning_updates(self) -> None:
        async with self._sessionmaker() as session:
            row = await session.get(MetaCounterRow, "learning_updates")
            if row is None:
                session.add(MetaCounterRow(key="learning_updates", value=1))
            else:
                row.value += 1
            await session.commit()

    async def get_stats(
        self,
        *,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> dict[str, Any]:
        async with self._sessionmaker() as session:
            stmt = select(AppealRow)
            if created_from is not None:
                stmt = stmt.where(AppealRow.created_at >= created_from)
            if created_to is not None:
                stmt = stmt.where(AppealRow.created_at <= created_to)
            appeals = list((await session.execute(stmt)).scalars().all())
            by_status = {s.value: 0 for s in AppealStatus}
            for a in appeals:
                by_status[a.status] = by_status.get(a.status, 0) + 1
            total = len(appeals) or 1
            msg_count = int(
                (
                    await session.execute(select(func.count()).select_from(MessageRow))
                ).scalar_one()
            )
            counter = await session.get(MetaCounterRow, "learning_updates")
            learning = int(counter.value) if counter else 0
            return {
                "appeals_total": len(appeals),
                "by_status": by_status,
                "messages_total": msg_count,
                "clarify_rate": by_status[AppealStatus.CLARIFYING.value] / total if appeals else 0.0,
                "escalation_rate": by_status[AppealStatus.ESCALATED.value] / total if appeals else 0.0,
                "answered_rate": by_status[AppealStatus.ANSWERED.value] / total if appeals else 0.0,
                "learning_updates": learning,
                "window": {
                    "from": created_from.isoformat() if created_from else None,
                    "to": created_to.isoformat() if created_to else None,
                },
            }

    async def _audit(
        self,
        session: AsyncSession,
        *,
        appeal_id: UUID | None,
        event_type: str,
        payload: dict[str, Any] | None,
    ) -> None:
        session.add(
            AuditEventRow(
                id=uuid4(),
                appeal_id=appeal_id,
                event_type=event_type,
                payload=payload or {},
                created_at=_utcnow(),
            )
        )

    @staticmethod
    def _to_appeal(row: AppealRow) -> Appeal:
        return Appeal(
            id=row.id,
            status=AppealStatus(row.status),
            created_at=row.created_at,
            updated_at=row.updated_at,
            user_id=row.user_id,
            user_label=row.user_label,
            topic=row.topic,
            summary=row.summary,
            escalation_id=row.escalation_id,
        )

    @staticmethod
    def _to_message(row: MessageRow) -> Message:
        raw = row.citations or []
        cites = [
            ChunkCitation(
                document_id=c["document_id"],
                chunk_id=c["chunk_id"],
                quote=c["quote"],
                score=c.get("score"),
                document_title=c.get("document_title"),
                locator=c.get("locator"),
            )
            for c in raw
        ]
        return Message(
            id=row.id,
            appeal_id=row.appeal_id,
            role=MessageRole(row.role),
            message_kind=MessageKind(row.message_kind),
            content=row.content,
            created_at=row.created_at,
            citations=cites,
        )

    @staticmethod
    def _to_escalation(row: EscalationRow) -> Escalation:
        return Escalation(
            id=row.id,
            appeal_id=row.appeal_id,
            reason=row.reason,
            status=EscalationStatus(row.status),
            channel=row.channel,
            quality_notified_at=row.quality_notified_at,
            officer_reply_at=row.officer_reply_at,
        )


_: Persistence = SqlAlchemyPersistence(  # type: ignore[assignment]
    database_url="postgresql+asyncpg://rag:rag@127.0.0.1:5432/rag_agent"
)
