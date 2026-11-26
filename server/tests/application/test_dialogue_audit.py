"""
ANCHOR: tests.application.test_dialogue_audit
PURPOSE: dialogue_turn audit payload — latency, rerank, chunk_ids, reasons.
Dependencies: audit builder; DialogueService with Fake persistence
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.application.dialogue.audit import build_dialogue_turn_audit
from app.application.dialogue.graph import build_dialogue_graph
from app.application.dialogue.nodes import DialogueDeps, make_nodes
from app.application.dialogue.service import DialogueService
from app.application.grounding.service import GroundingService
from app.application.retrieval.service import RetrievalService
from app.domain.enums import AppealStatus, MessageKind, MessageRole
from app.domain.models import Appeal, Message

_NOW = datetime.now(timezone.utc)


def test_build_dialogue_turn_audit_answer_shape() -> None:
    payload = build_dialogue_turn_audit(
        outcome="answer",
        node_trace=["assess:specific", "retrieve:hits=1", "ground:ok", "answer"],
        specificity="specific",
        citations=[
            {
                "chunk_id": "c-1",
                "document_id": "reg-1",
                "score": 0.91,
            }
        ],
        candidates=[{"chunk_id": "c-1", "document_id": "reg-1", "score": 0.91}],
        rerank_mode="llm",
        rerank_scores=[{"chunk_id": "c-1", "document_id": "reg-1", "score": 0.91}],
        latency_ms={
            "llm_assess_ms": 1.0,
            "llm_complete_ms": 2.0,
            "retrieval_total_ms": 3.0,
            "turn_total_ms": 10.0,
        },
    )
    assert payload["outcome"] == "answer"
    assert payload["chunk_ids"] == ["c-1"]
    assert payload["rerank"]["mode"] == "llm"
    assert payload["rerank"]["scores"][0]["score"] == 0.91
    assert payload["latency_ms"]["llm_assess_ms"] == 1.0
    assert payload["escalation_reason"] is None
    assert payload["clarify_reason"] is None


def test_build_dialogue_turn_audit_clarify_and_escalate_reasons() -> None:
    clarify = build_dialogue_turn_audit(
        outcome="clarify",
        node_trace=["assess:ambiguous", "clarify:ambiguous"],
        specificity="ambiguous",
        clarify_reason="ambiguous",
    )
    assert clarify["clarify_reason"] == "ambiguous"
    assert clarify["escalation_reason"] is None

    esc = build_dialogue_turn_audit(
        outcome="escalate",
        node_trace=["assess:specific", "ground:fail:insufficient_citations"],
        escalation_reason="insufficient_citations",
    )
    assert esc["escalation_reason"] == "insufficient_citations"


@pytest.mark.asyncio
async def test_retrieve_node_records_rerank_and_latency() -> None:
    hits = [
        {
            "document_id": "d1",
            "chunk_id": "c1",
            "text": "chunk text",
            "score": 0.8,
        }
    ]
    emb = AsyncMock(embed_dense=AsyncMock(return_value=[[0.1]]))
    vs = AsyncMock(search=AsyncMock(return_value=hits))
    deps = DialogueDeps(
        llm=AsyncMock(),
        retrieval=RetrievalService(embeddings=emb, vectorstore=vs, rerank_mode="none"),
        grounding=GroundingService(),
        quality_email="q@example.invalid",
    )
    nodes = make_nodes(deps)
    out = await nodes["retrieve"]({"user_message": "q", "history": [], "latency_ms": {}})
    assert out["candidates"][0]["chunk_id"] == "c1"
    assert out["rerank_mode"] == "none"
    assert out["rerank_scores"][0]["chunk_id"] == "c1"
    assert "retrieval_total_ms" in out["latency_ms"]
    assert "embed_ms" in out["latency_ms"]
    assert "search_ms" in out["latency_ms"]


@pytest.mark.asyncio
async def test_dialogue_service_persists_enriched_audit() -> None:
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
        content="Кто подписывает договоры на закупку?",
        created_at=_NOW,
    )
    assistant_msg = Message(
        id=uuid4(),
        appeal_id=appeal_id,
        role=MessageRole.ASSISTANT,
        message_kind=MessageKind.ANSWER,
        content="answer",
        created_at=_NOW,
    )

    persistence = MagicMock()
    persistence.get_appeal = AsyncMock(return_value=appeal)
    persistence.add_message = AsyncMock(side_effect=[user_msg, assistant_msg])
    persistence.list_messages = AsyncMock(return_value=[user_msg])
    persistence.update_appeal = AsyncMock(
        return_value=Appeal(
            id=appeal_id,
            status=AppealStatus.ANSWERED,
            created_at=_NOW,
            updated_at=_NOW,
            summary="answer",
        )
    )
    persistence.add_audit_event = AsyncMock()

    hits = [
        {
            "document_id": "reg-1",
            "chunk_id": "c-1",
            "text": "Договоры на закупку подписывает директор по закупкам.",
            "score": 0.91,
            "document_title": "Регламент закупок",
            "source": "ingest",
        }
    ]

    class _LLM:
        async def classify_specificity(
            self, user_message: str, history: list[str] | None = None
        ) -> str:
            return "specific"

        complete = AsyncMock(return_value="draft")

    deps = DialogueDeps(
        llm=_LLM(),
        retrieval=RetrievalService(
            embeddings=AsyncMock(embed_dense=AsyncMock(return_value=[[0.1]])),
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
    persistence.add_audit_event.assert_awaited()
    kwargs = persistence.add_audit_event.await_args.kwargs
    assert kwargs["event_type"] == "dialogue_turn"
    payload: dict[str, Any] = kwargs["payload"]
    assert payload["outcome"] == "answer"
    assert "c-1" in payload["chunk_ids"]
    assert payload["latency_ms"]["turn_total_ms"] >= 0
    assert "llm_assess_ms" in payload["latency_ms"]
    assert payload["rerank"]["mode"] == "none"
    assert payload["rerank"]["scores"]


@pytest.mark.asyncio
async def test_graph_clarify_sets_reason() -> None:
    class _LLM:
        async def classify_specificity(
            self, user_message: str, history: list[str] | None = None
        ) -> str:
            return "underspecified"

        complete = AsyncMock()

    deps = DialogueDeps(
        llm=_LLM(),
        retrieval=RetrievalService(
            embeddings=AsyncMock(embed_dense=AsyncMock(return_value=[[0.1]])),
            vectorstore=AsyncMock(search=AsyncMock(return_value=[])),
        ),
        grounding=GroundingService(),
        quality_email="q@example.invalid",
    )
    graph = build_dialogue_graph(deps)
    out = await graph.ainvoke(
        {
            "user_message": "?",
            "history": [],
            "clarify_turns": 0,
            "max_clarify_turns": 3,
        }
    )
    assert out["outcome"] == "clarify"
    assert out["clarify_reason"] == "underspecified"
