"""
ANCHOR: app.adapters.persistence.sqlalchemy.models
PURPOSE: SQLAlchemy ORM models for appeals, messages, escalations, audit.
Dependencies: sqlalchemy
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


# JSONB on Postgres; JSON elsewhere (sqlite emergency fallback).
JSONType = JSON().with_variant(JSONB(), "postgresql")


class AppealRow(Base):
    __tablename__ = "appeals"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    user_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    topic: Mapped[str | None] = mapped_column(String(512), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    escalation_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    messages: Mapped[list[MessageRow]] = relationship(back_populates="appeal")


class MessageRow(Base):
    __tablename__ = "messages"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    appeal_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appeals.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    message_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    citations: Mapped[dict | list | None] = mapped_column(JSONType, nullable=True)

    appeal: Mapped[AppealRow] = relationship(back_populates="messages")


class EscalationRow(Base):
    __tablename__ = "escalations"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    appeal_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appeals.id", ondelete="CASCADE"), index=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(64), nullable=False, default="email")
    quality_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    officer_reply_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEventRow(Base):
    __tablename__ = "audit_events"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    appeal_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    payload: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MetaCounterRow(Base):
    __tablename__ = "meta_counters"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
