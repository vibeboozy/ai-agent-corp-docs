"""
ANCHOR: tests.application.test_demo_scenarios
PURPOSE: Exact DEMO.md dialogue scenarios via Fake ports (offline).
Dependencies: dialogue.graph; Fake LLM/embeddings/vectorstore
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
        self.complete = AsyncMock(side_effect=self._complete)

    async def _complete(self, *, system: str, user: str, temperature: float | None = None) -> str:
        _ = (system, temperature)
        if "Reason:" in user:
            return "Уточните, пожалуйста, тему и что именно нужно узнать."
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
        return [{"токен": 1.0} for _ in texts]


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


class TestDemoExactFlow:
    """Точные сценарии из DEMO.md — один вызов graph.ainvoke() с нужными входными данными."""

    @pytest.mark.asyncio
    async def test_demo_scenario_1_direct_answer(self) -> None:
        """DEMO.md Сценарий 1: конкретный вопрос сразу даёт ответ с цитатами.

        "Кто отвечает за организацию отчётности по проекту?"
        → specific + hits → answered
        """
        hits = [
            {
                "document_id": "reg-projects",
                "chunk_id": "chunk-otchetnost",
                "text": "Отчётность по проекту ведёт координатор проекта.",
                "score": 0.93,
                "document_title": "Регламент проектов",
                "source": "ingest",
            }
        ]
        graph = build_dialogue_graph(_deps(label="specific", hits=hits))
        out = await graph.ainvoke(
            {
                "user_message": "Кто отвечает за организацию отчётности по проекту?",
                "history": [],
                "clarify_turns": 0,
                "max_clarify_turns": 3,
            }
        )
        assert out["outcome"] == "answer", (
            f"Ожидался answer, получил {out['outcome']}. "
            f"node_trace={out['node_trace']}"
        )
        assert out["grounded"] is True
        assert out["citations"]
        assert out["citations"][0]["chunk_id"] == "chunk-otchetnost"
        assert any("assess:specific" in t for t in out["node_trace"])
        assert "retrieve:hits=1" in out["node_trace"]
        assert "ground:ok" in out["node_trace"]

    @pytest.mark.asyncio
    async def test_demo_scenario_2_clarify_then_answer(self) -> None:
        """DEMO.md Сценарий 2: полный цикл уточнения.

        Шаг 1: "Кто отвечает за организацию?" → underspecified → clarification
        Шаг 2: "Это про отчётность по проекту." + history → specific → answer
        """
        hits = [
            {
                "document_id": "reg-projects",
                "chunk_id": "chunk-otchetnost",
                "text": "Отчётность по проекту ведёт координатор проекта.",
                "score": 0.93,
                "document_title": "Регламент проектов",
                "source": "ingest",
            }
        ]
        graph_clarify = build_dialogue_graph(_deps(label="underspecified", hits=[]))
        graph_answer = build_dialogue_graph(_deps(label="specific", hits=hits))

        step1_out = await graph_clarify.ainvoke(
            {
                "user_message": "Кто отвечает за организацию?",
                "history": [],
                "clarify_turns": 0,
                "max_clarify_turns": 3,
            }
        )
        assert step1_out["outcome"] == "clarify", (
            f"Шаг 1: ожидался clarify, получил {step1_out['outcome']}. "
            f"node_trace={step1_out['node_trace']}"
        )
        assert step1_out["clarify_reason"] in ("underspecified", "ambiguous")

        step2_out = await graph_answer.ainvoke(
            {
                "user_message": "Это про отчётность по проекту.",
                "history": ["Кто отвечает за организацию?"],
                "clarify_turns": 1,
                "max_clarify_turns": 3,
            }
        )
        assert step2_out["outcome"] == "answer", (
            f"Шаг 2: ожидался answer, получил {step2_out['outcome']}. "
            f"node_trace={step2_out['node_trace']}"
        )
        assert step2_out["grounded"] is True
        assert step2_out["citations"]
