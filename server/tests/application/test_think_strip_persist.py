"""
ANCHOR: tests.application.test_think_strip_persist
PURPOSE: First-generate path strips <think> before save of answer + summary.
Dependencies: DialogueService; Fake LLM with dirty draft (no live URLs)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.application.dialogue.nodes import DialogueDeps
from app.application.dialogue.service import DialogueService
from app.application.grounding.service import GroundingService
from app.application.retrieval.service import RetrievalService
from app.domain.enums import AppealStatus, MessageKind, MessageRole
from app.domain.models import Appeal, Message

_NOW = datetime.now(timezone.utc)

_DIRTY_DRAFT = (
    "<think>\n"
    "The question is about who plans risks. I will cite the regulation.\n"
    "</think>\n"
    "За планирование рисков отвечает руководитель проекта."
)


@pytest.mark.asyncio
async def test_first_answer_persists_stripped_content_and_summary() -> None:
    """Reproduce: first LLM completion has <think>; API fields must be clean."""
    appeal_id = uuid4()
    appeal = Appeal(
        id=appeal_id,
        status=AppealStatus.OPEN,
        created_at=_NOW,
        updated_at=_NOW,
    )
    user_msg = Message(
        id=uuid4(),
        appeal_id=appeal_id,
        role=MessageRole.USER,
        message_kind=MessageKind.QUESTION,
        content="Кто планирует риски?",
        created_at=_NOW,
    )
    assistant_holder: dict[str, Any] = {}

    async def _add_message(**kwargs: Any) -> Message:
        msg = Message(
            id=uuid4(),
            appeal_id=appeal_id,
            role=kwargs["role"],
            message_kind=kwargs["message_kind"],
            content=kwargs["content"],
            citations=kwargs.get("citations"),
            created_at=_NOW,
        )
        if kwargs["role"] == MessageRole.ASSISTANT:
            assistant_holder["msg"] = msg
            assistant_holder["content"] = kwargs["content"]
        return msg

    async def _update_appeal(aid, **kwargs: Any) -> Appeal:
        _ = aid
        assistant_holder["summary"] = kwargs.get("summary")
        return Appeal(
            id=appeal_id,
            status=kwargs.get("status", AppealStatus.ANSWERED),
            created_at=_NOW,
            updated_at=_NOW,
            summary=kwargs.get("summary"),
        )

    persistence = MagicMock()
    persistence.get_appeal = AsyncMock(return_value=appeal)
    persistence.add_message = AsyncMock(side_effect=_add_message)
    persistence.list_messages = AsyncMock(return_value=[])
    persistence.update_appeal = AsyncMock(side_effect=_update_appeal)
    persistence.add_audit_event = AsyncMock()

    chunk = "За планирование рисков отвечает руководитель проекта."
    hits = [
        {
            "document_id": "reg-risk",
            "chunk_id": "c-risk",
            "text": chunk,
            "score": 0.94,
            "document_title": "Регламент рисков",
            "source": "ingest",
        }
    ]

    class _LLM:
        async def classify_specificity(
            self, user_message: str, history: list[str] | None = None
        ) -> str:
            _ = (user_message, history)
            return "specific"

        complete = AsyncMock(return_value=_DIRTY_DRAFT)

    deps = DialogueDeps(
        llm=_LLM(),
        retrieval=RetrievalService(
            embeddings=AsyncMock(
                embed_dense=AsyncMock(return_value=[[0.1]]),
                embed_sparse=AsyncMock(return_value=[{"риск": 1.0}]),
            ),
            vectorstore=AsyncMock(search=AsyncMock(return_value=hits)),
        ),
        grounding=GroundingService(min_citations=1, min_score=0.0),
        quality_email="quality@example.invalid",
    )
    escalation = MagicMock()
    svc = DialogueService(
        persistence=persistence,
        deps=deps,
        escalation=escalation,
        max_clarify_turns=3,
    )
    result = await svc.run_turn(appeal_id=appeal_id, content=user_msg.content)

    assert result.outcome == "answer"
    content = assistant_holder["content"]
    summary = assistant_holder["summary"]
    assert "<think>" not in content.lower()
    assert "</think>" not in content.lower()
    assert "<think>" not in (summary or "").lower()
    assert "руководитель проекта" in content
    assert "уководитель проекта" in (summary or "").lower()
    # Summary derived from the same cleaned answer text.
    assert summary == content or (summary or "") in content
