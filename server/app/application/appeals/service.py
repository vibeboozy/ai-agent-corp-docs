"""
ANCHOR: app.application.appeals.service
PURPOSE: Appeal lifecycle: create/list/get and optional first dialogue turn.
Dependencies: domain, persistence port, dialogue service
DO:
- Persist status transitions with audit
DONT:
- Call LLM or vector store from appeals service directly
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.adapters.persistence.port import Persistence
from app.application.dialogue.service import DialogueService, DialogueTurnResult
from app.domain.enums import AppealStatus, MessageRole
from app.domain.errors import NotFoundError
from app.domain.models import Appeal, Message


@dataclass
class AppealView:
    appeal: Appeal
    message_count: int
    question: str | None = None


@dataclass
class CreateAppealResult:
    appeal: Appeal
    messages: list[Message]
    message_count: int
    question: str | None = None


def _question_from_messages(messages: list[Message]) -> str | None:
    for m in messages:
        if m.role == MessageRole.USER and m.content and m.content.strip():
            return m.content.strip()
    return None


class AppealsService:
    def __init__(
        self,
        *,
        persistence: Persistence,
        dialogue: DialogueService,
    ) -> None:
        self._persistence = persistence
        self._dialogue = dialogue

    async def create(
        self,
        *,
        user_id: str | None = None,
        user_label: str | None = None,
        topic: str | None = None,
        first_message: str | None = None,
    ) -> CreateAppealResult:
        # Prefer explicit topic; otherwise derive from the first user message so
        # quality-cabinet list never falls back to AI summary as the "question".
        resolved_topic = topic
        if not (resolved_topic and resolved_topic.strip()) and first_message:
            resolved_topic = first_message.strip()[:120]

        appeal = await self._persistence.create_appeal(
            user_id=user_id,
            user_label=user_label,
            topic=resolved_topic,
            status=AppealStatus.OPEN,
        )
        messages: list[Message] = []
        if first_message:
            turn: DialogueTurnResult = await self._dialogue.run_turn(
                appeal_id=appeal.id,
                content=first_message,
            )
            appeal = turn.appeal
            messages = turn.messages
        count = await self._persistence.count_messages(appeal.id)
        question = _question_from_messages(messages) or (
            first_message.strip() if first_message else None
        ) or appeal.topic
        return CreateAppealResult(
            appeal=appeal,
            messages=messages,
            message_count=count,
            question=question,
        )

    async def get(self, appeal_id: UUID) -> AppealView:
        appeal = await self._persistence.get_appeal(appeal_id)
        if appeal is None:
            raise NotFoundError(f"Appeal {appeal_id} not found")
        count = await self._persistence.count_messages(appeal_id)
        questions = await self._persistence.first_user_messages([appeal_id])
        question = questions.get(appeal_id) or appeal.topic
        return AppealView(appeal=appeal, message_count=count, question=question)

    async def list(
        self,
        *,
        status: AppealStatus | None = None,
        user_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> tuple[list[AppealView], int]:
        appeals, total = await self._persistence.list_appeals(
            status=status,
            user_id=user_id,
            limit=limit,
            offset=offset,
            created_from=created_from,
            created_to=created_to,
        )
        ids = [a.id for a in appeals]
        questions = await self._persistence.first_user_messages(ids)
        views: list[AppealView] = []
        for a in appeals:
            count = await self._persistence.count_messages(a.id)
            question = questions.get(a.id) or a.topic
            views.append(
                AppealView(appeal=a, message_count=count, question=question)
            )
        return views, total

    async def list_messages(
        self,
        appeal_id: UUID,
        *,
        after_id: UUID | None = None,
        limit: int = 100,
    ) -> list[Message]:
        if await self._persistence.get_appeal(appeal_id) is None:
            raise NotFoundError(f"Appeal {appeal_id} not found")
        return await self._persistence.list_messages(
            appeal_id, after_id=after_id, limit=limit
        )

    async def post_message(
        self, *, appeal_id: UUID, content: str
    ) -> DialogueTurnResult:
        return await self._dialogue.run_turn(appeal_id=appeal_id, content=content)
