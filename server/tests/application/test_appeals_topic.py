"""
ANCHOR: tests.application.test_appeals_topic
PURPOSE: Appeal create derives topic from first message; list limit > 50.
Dependencies: AppealsService + fake persistence
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.application.appeals.service import AppealsService
from app.domain.enums import AppealStatus, MessageKind, MessageRole
from app.domain.models import Appeal, Message


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _FakePersistence:
    def __init__(self) -> None:
        self.appeals: dict[UUID, Appeal] = {}
        self.messages: list[Message] = []

    async def create_appeal(self, **kwargs: Any) -> Appeal:
        aid = uuid4()
        appeal = Appeal(
            id=aid,
            status=kwargs.get("status", AppealStatus.OPEN),
            created_at=_now(),
            updated_at=_now(),
            user_id=kwargs.get("user_id"),
            user_label=kwargs.get("user_label"),
            topic=kwargs.get("topic"),
            summary=None,
            escalation_id=None,
        )
        self.appeals[aid] = appeal
        return appeal

    async def get_appeal(self, appeal_id: UUID) -> Appeal | None:
        return self.appeals.get(appeal_id)

    async def update_appeal(self, appeal_id: UUID, **kwargs: Any) -> Appeal:
        a = self.appeals[appeal_id]
        data = a.__dict__.copy()
        data.update(kwargs)
        data["updated_at"] = _now()
        updated = Appeal(**data)
        self.appeals[appeal_id] = updated
        return updated

    async def add_message(self, **kwargs: Any) -> Message:
        msg = Message(
            id=uuid4(),
            appeal_id=kwargs["appeal_id"],
            role=kwargs["role"],
            message_kind=kwargs["message_kind"],
            content=kwargs["content"],
            created_at=_now(),
            citations=kwargs.get("citations") or [],
        )
        self.messages.append(msg)
        return msg

    async def count_messages(self, appeal_id: UUID) -> int:
        return sum(1 for m in self.messages if m.appeal_id == appeal_id)

    async def list_messages(
        self, appeal_id: UUID, *, after_id: UUID | None = None, limit: int = 100
    ) -> list[Message]:
        return [m for m in self.messages if m.appeal_id == appeal_id][:limit]

    async def list_appeals(self, **kwargs: Any) -> tuple[list[Appeal], int]:
        items = list(self.appeals.values())
        limit = int(kwargs.get("limit") or 50)
        return items[:limit], len(items)


class _FakeDialogue:
    def __init__(self, persistence: _FakePersistence) -> None:
        self._p = persistence

    async def run_turn(self, *, appeal_id: UUID, content: str) -> Any:
        from app.application.dialogue.service import DialogueTurnResult

        user = await self._p.add_message(
            appeal_id=appeal_id,
            role=MessageRole.USER,
            message_kind=MessageKind.QUESTION,
            content=content,
        )
        refusal = "Этот вопрос не поддерживается."
        assistant = await self._p.add_message(
            appeal_id=appeal_id,
            role=MessageRole.ASSISTANT,
            message_kind=MessageKind.REFUSAL,
            content=refusal,
        )
        appeal = await self._p.update_appeal(
            appeal_id,
            status=AppealStatus.ANSWERED,
            summary=refusal,
        )
        return DialogueTurnResult(
            appeal=appeal,
            messages=[user, assistant],
            outcome="refuse",
            node_trace=["assess", "refuse"],
        )


@pytest.mark.asyncio
async def test_create_derives_topic_from_first_message_when_missing() -> None:
    persistence = _FakePersistence()
    dialogue = _FakeDialogue(persistence)
    svc = AppealsService(persistence=persistence, dialogue=dialogue)  # type: ignore[arg-type]

    result = await svc.create(
        topic=None,
        first_message="Сколько времени в Москве?",
    )

    assert result.appeal.topic == "Сколько времени в Москве?"
    assert result.appeal.status == AppealStatus.ANSWERED
    assert result.appeal.summary == "Этот вопрос не поддерживается."
    # Topic must remain the employee question, not the AI summary
    assert result.appeal.topic != result.appeal.summary


@pytest.mark.asyncio
async def test_create_keeps_explicit_topic() -> None:
    persistence = _FakePersistence()
    dialogue = _FakeDialogue(persistence)
    svc = AppealsService(persistence=persistence, dialogue=dialogue)  # type: ignore[arg-type]

    result = await svc.create(
        topic="Лицензии",
        first_message="Как перенести лицензию?",
    )
    assert result.appeal.topic == "Лицензии"


@pytest.mark.asyncio
async def test_list_respects_limit_above_50() -> None:
    persistence = _FakePersistence()
    for i in range(60):
        await persistence.create_appeal(topic=f"q-{i}", status=AppealStatus.ANSWERED)

    dialogue = _FakeDialogue(persistence)
    svc = AppealsService(persistence=persistence, dialogue=dialogue)  # type: ignore[arg-type]

    views, total = await svc.list(limit=200)
    assert total == 60
    assert len(views) == 60
