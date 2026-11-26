"""initial schema: appeals, messages, escalations, audit_events

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-26
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "appeals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("user_id", sa.String(255), nullable=True),
        sa.Column("user_label", sa.String(255), nullable=True),
        sa.Column("topic", sa.String(512), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("escalation_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_appeals_status", "appeals", ["status"])
    op.create_index("ix_appeals_user_id", "appeals", ["user_id"])

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("appeal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("appeals.id", ondelete="CASCADE")),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("message_kind", sa.String(64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("citations", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_messages_appeal_id", "messages", ["appeal_id"])

    op.create_table(
        "escalations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("appeal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("appeals.id", ondelete="CASCADE")),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("channel", sa.String(64), nullable=False, server_default="email"),
        sa.Column("quality_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("officer_reply_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_escalations_appeal_id", "escalations", ["appeal_id"])
    op.create_index("ix_escalations_status", "escalations", ["status"])

    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("appeal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_audit_events_appeal_id", "audit_events", ["appeal_id"])
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])

    op.create_table(
        "meta_counters",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("meta_counters")
    op.drop_table("audit_events")
    op.drop_table("escalations")
    op.drop_table("messages")
    op.drop_table("appeals")
