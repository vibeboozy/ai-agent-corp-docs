"""
ANCHOR: tests.application.test_dialogue_flows
PURPOSE: Stub behavior tests — grounded / clarify / escalate / officer learning.
Dependencies: application services via DI container
"""

from __future__ import annotations

import pytest

from app.adapters.stubs.fixtures import SHARED_FIXTURE_KB
from app.config.factories import build_container
from app.config.settings import Settings
from app.domain.enums import AppealStatus, MessageKind


@pytest.fixture
def container():
    SHARED_FIXTURE_KB.reset()
    settings = Settings(USE_STUBS=True, PERSISTENCE_USE_STUB=True)
    return build_container(settings)


@pytest.mark.asyncio
async def test_grounded_answer_with_citations(container) -> None:
    created = await container.appeals.create(
        first_message="Кто подписывает договоры на закупку?"
    )
    assert created.appeal.status == AppealStatus.ANSWERED
    kinds = [m.message_kind for m in created.messages]
    assert MessageKind.QUESTION in kinds
    assert MessageKind.ANSWER in kinds
    answer = next(m for m in created.messages if m.message_kind == MessageKind.ANSWER)
    assert answer.citations, "grounded answers must include citations"
    assert "директор по закупкам" in answer.content.lower() or "закуп" in answer.content.lower()


@pytest.mark.asyncio
async def test_ambiguous_question_clarifies(container) -> None:
    created = await container.appeals.create(
        first_message="Кто подписывает договоры?"
    )
    assert created.appeal.status == AppealStatus.CLARIFYING
    clarify = next(
        m for m in created.messages if m.message_kind == MessageKind.CLARIFICATION
    )
    assert "уточн" in clarify.content.lower() or "закуп" in clarify.content.lower()


@pytest.mark.asyncio
async def test_unknown_topic_escalates_without_invention(container) -> None:
    created = await container.appeals.create(
        first_message="Какой цвет логотипа у конкурентов согласно брендбуку компании?"
    )
    assert created.appeal.status == AppealStatus.ESCALATED
    notice = next(
        m for m in created.messages if m.message_kind == MessageKind.ESCALATION_NOTICE
    )
    assert "качеств" in notice.content.lower()
    # Must not invent a brand color
    assert "синий" not in notice.content.lower()
    assert created.appeal.escalation_id is not None


@pytest.mark.asyncio
async def test_officer_learning_then_answer(container) -> None:
    created = await container.appeals.create(
        first_message="Какой цвет логотипа у конкурентов согласно брендбуку компании?"
    )
    assert created.appeal.status == AppealStatus.ESCALATED

    learned = await container.learning.officer_reply(
        appeal_id=created.appeal.id,
        content=(
            "Согласно внутреннему брендбуку, логотип конкурентов в материалах компании "
            "не используется; фирменный цвет нашего логотипа — тёмно-зелёный Pantone 3435."
        ),
        source_document_hint="brandbook-internal",
    )
    assert learned.accepted is True
    assert learned.ingest_job_id
    assert learned.appeal.status == AppealStatus.RESOLVED_BY_OFFICER

    follow = await container.appeals.create(
        first_message="Какой цвет логотипа указан в брендбуке компании?"
    )
    assert follow.appeal.status == AppealStatus.ANSWERED
    answer = next(m for m in follow.messages if m.message_kind == MessageKind.ANSWER)
    assert answer.citations
    assert "зелён" in answer.content.lower() or "pantone" in answer.content.lower()


@pytest.mark.asyncio
async def test_dialogue_graph_compiles(container) -> None:
    from app.application.dialogue.graph import build_dialogue_graph
    from app.application.dialogue.nodes import DialogueDeps
    from app.application.grounding.service import GroundingService
    from app.application.retrieval.service import RetrievalService

    deps = DialogueDeps(
        llm=container.llm,
        retrieval=RetrievalService(
            embeddings=container.embeddings, vectorstore=container.vectorstore
        ),
        grounding=GroundingService(),
        quality_email="quality@example.invalid",
    )
    graph = build_dialogue_graph(deps)
    assert graph is not None
