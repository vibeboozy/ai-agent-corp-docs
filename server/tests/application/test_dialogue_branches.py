"""
ANCHOR: tests.application.test_dialogue_branches
PURPOSE: Offline LangGraph branches — clarify / grounded answer / escalate via Fake ports.
Dependencies: dialogue.graph; MagicMock / Fake adapters (no live URLs)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.application.dialogue.graph import build_dialogue_graph
from app.application.dialogue.nodes import DialogueDeps
from app.application.grounding.service import GroundingService
from app.application.retrieval.service import RetrievalService


class _FakeLLM:
    def __init__(self, *, label: str, draft: str = "draft") -> None:
        self._label = label
        self._draft = draft
        self.complete = AsyncMock(
            side_effect=self._complete,
        )

    async def _complete(self, *, system: str, user: str, temperature: float | None = None) -> str:
        _ = temperature
        if "clarifying" in system.lower() or "Reason:" in user:
            if "ambiguous" in user.lower():
                return (
                    "Уточните, пожалуйста: речь о договорах на закупку или о договорах "
                    "с подрядчиками?"
                )
            return (
                "Вопрос сформулирован недостаточно конкретно. Укажите, пожалуйста, "
                "тип процесса и что именно нужно узнать."
            )
        return self._draft

    async def classify_specificity(
        self, user_message: str, history: list[str] | None = None
    ) -> str:
        _ = (user_message, history)
        return self._label


class _FakeEmbeddings:
    async def embed_dense(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]

    async def embed_sparse(self, texts: list[str]) -> list[dict[str, float]]:
        return [{t: 1.0 for t in (text.lower().split()[:3] or ["x"])} for text in texts]


class _FakeVectorStore:
    def __init__(self, hits: list[dict[str, Any]]) -> None:
        self._hits = hits

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
        dense_vector: list[float] | None = None,
        sparse_vector: dict[str, float] | None = None,
    ) -> list[dict[str, Any]]:
        _ = (query, limit, dense_vector, sparse_vector)
        return list(self._hits)


def _deps(*, label: str, hits: list[dict[str, Any]]) -> DialogueDeps:
    return DialogueDeps(
        llm=_FakeLLM(label=label),
        retrieval=RetrievalService(
            embeddings=_FakeEmbeddings(),
            vectorstore=_FakeVectorStore(hits),
        ),
        grounding=GroundingService(min_citations=1, min_score=0.0),
        quality_email="quality@example.invalid",
    )


@pytest.mark.asyncio
async def test_graph_underspecified_clarifies() -> None:
    graph = build_dialogue_graph(_deps(label="underspecified", hits=[]))
    out = await graph.ainvoke(
        {
            "user_message": "Кто подписывает договоры?",
            "history": [],
            "clarify_turns": 0,
            "max_clarify_turns": 3,
        }
    )
    assert out["outcome"] == "clarify"
    assert out["clarification_text"]
    assert any("assess:underspecified" in t for t in out["node_trace"])
    assert any(t.startswith("retrieve:") for t in out["node_trace"])
    assert any(t.startswith("clarify") for t in out["node_trace"])
    assert out.get("clarify_reason") == "underspecified"


@pytest.mark.asyncio
async def test_graph_ambiguous_clarifies_with_options() -> None:
    graph = build_dialogue_graph(_deps(label="ambiguous", hits=[]))
    out = await graph.ainvoke(
        {
            "user_message": "Кто подписывает договоры?",
            "history": [],
            "clarify_turns": 0,
            "max_clarify_turns": 3,
        }
    )
    assert out["outcome"] == "clarify"
    assert "закупк" in out["clarification_text"].lower()


@pytest.mark.asyncio
async def test_graph_specific_with_hits_answers_grounded() -> None:
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
    graph = build_dialogue_graph(_deps(label="specific", hits=hits))
    out = await graph.ainvoke(
        {
            "user_message": "Кто подписывает договоры на закупку?",
            "history": [],
            "clarify_turns": 0,
            "max_clarify_turns": 3,
        }
    )
    assert out["outcome"] == "answer"
    assert out["grounded"] is True
    assert out["citations"]
    assert out["citations"][0]["chunk_id"] == "c-1"
    assert "ground:ok" in out["node_trace"]


@pytest.mark.asyncio
async def test_graph_specific_without_hits_escalates() -> None:
    graph = build_dialogue_graph(_deps(label="specific", hits=[]))
    out = await graph.ainvoke(
        {
            "user_message": "Какой цвет логотипа у конкурентов?",
            "history": [],
            "clarify_turns": 0,
            "max_clarify_turns": 3,
        }
    )
    assert out["outcome"] == "escalate"
    assert out["escalation_reason"] == "insufficient_citations"
    assert out["quality_email"] == "quality@example.invalid"


@pytest.mark.asyncio
async def test_graph_max_clarify_exceeded_escalates() -> None:
    graph = build_dialogue_graph(_deps(label="underspecified", hits=[]))
    out = await graph.ainvoke(
        {
            "user_message": "?",
            "history": [],
            "clarify_turns": 3,
            "max_clarify_turns": 3,
        }
    )
    assert out["outcome"] == "escalate"
    assert out["escalation_reason"] == "max_clarify_exceeded"
