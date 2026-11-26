"""
ANCHOR: tests.application.test_clarify_bias_regression
PURPOSE: Role+topic questions must answer when KB hits exist; vague → clarify.
Dependencies: dialogue.graph; Fake ports; specificity helpers
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.application.dialogue.graph import build_dialogue_graph
from app.application.dialogue.nodes import DialogueDeps
from app.application.dialogue.specificity import (
    looks_role_topic_specific,
    prefer_specific_label,
)
from app.application.grounding.service import GroundingService
from app.application.retrieval.service import RetrievalService


class _FakeLLM:
    """Always returns a timid underspecified label — exercises assess override."""

    def __init__(self, *, label: str = "underspecified") -> None:
        self._label = label
        self.complete = AsyncMock(return_value="Согласно регламенту: РП.")

    async def classify_specificity(
        self, user_message: str, history: list[str] | None = None
    ) -> str:
        _ = (user_message, history)
        return self._label


class _FakeEmbeddings:
    async def embed_dense(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2] for _ in texts]


class _FakeVectorStore:
    def __init__(self, hits: list[dict[str, Any]]) -> None:
        self._hits = hits

    async def search(
        self, query: str, *, limit: int = 5, dense_vector: list[float] | None = None
    ) -> list[dict[str, Any]]:
        _ = (query, limit, dense_vector)
        return list(self._hits)


def _deps(*, label: str, hits: list[dict[str, Any]]) -> DialogueDeps:
    return DialogueDeps(
        llm=_FakeLLM(label=label),
        retrieval=RetrievalService(
            embeddings=_FakeEmbeddings(),
            vectorstore=_FakeVectorStore(hits),
            rerank_min_score=0.0,
        ),
        grounding=GroundingService(min_citations=1, min_score=0.0),
        quality_email="quality@example.invalid",
    )


_OTCHET_HIT = {
    "document_id": "reg-projects",
    "chunk_id": "chunk-rp",
    "text": "РП — руководитель проекта отвечает за организацию отчётности по проекту.",
    "score": 0.95,
    "document_title": "Регламент проектов",
    "source": "ingest",
}


def test_looks_role_topic_specific_examples() -> None:
    assert looks_role_topic_specific(
        "Кто отвечает за организацию отчётности по проекту?"
    )
    assert not looks_role_topic_specific("Кто отвечает за организацию?")
    assert looks_role_topic_specific(
        "Это про отчётность по проекту.",
        history=["Кто отвечает за организацию?"],
    )
    assert prefer_specific_label(
        "underspecified", "Кто отвечает за организацию отчётности по проекту?"
    ) == "specific"
    assert (
        prefer_specific_label("underspecified", "Кто отвечает за организацию?")
        == "underspecified"
    )


@pytest.mark.asyncio
async def test_specific_role_topic_with_hits_answers_despite_timid_llm() -> None:
    """Regression: KB has the answer but timid classify used to force clarify forever."""
    graph = build_dialogue_graph(_deps(label="underspecified", hits=[_OTCHET_HIT]))
    out = await graph.ainvoke(
        {
            "user_message": "Кто отвечает за организацию отчётности по проекту?",
            "history": [],
            "clarify_turns": 0,
            "max_clarify_turns": 3,
        }
    )
    assert out["outcome"] == "answer", out["node_trace"]
    assert out["grounded"] is True
    assert out["citations"]
    assert any("assess:specific" in t for t in out["node_trace"])
    assert "retrieve:hits=1" in out["node_trace"]


@pytest.mark.asyncio
async def test_underspecified_without_topic_still_clarifies() -> None:
    graph = build_dialogue_graph(_deps(label="underspecified", hits=[_OTCHET_HIT]))
    out = await graph.ainvoke(
        {
            "user_message": "Кто отвечает за организацию?",
            "history": [],
            "clarify_turns": 0,
            "max_clarify_turns": 3,
        }
    )
    assert out["outcome"] == "clarify"
    assert out["clarify_reason"] == "underspecified"
    # Must not retrieve on true underspecified — hits must not short-circuit clarify.
    assert not any(t.startswith("retrieve:") for t in out["node_trace"])


@pytest.mark.asyncio
async def test_clarification_plus_history_overrides_timid_label() -> None:
    graph = build_dialogue_graph(_deps(label="underspecified", hits=[_OTCHET_HIT]))
    out = await graph.ainvoke(
        {
            "user_message": "Это про отчётность по проекту.",
            "history": ["Кто отвечает за организацию?"],
            "clarify_turns": 1,
            "max_clarify_turns": 3,
        }
    )
    assert out["outcome"] == "answer", out["node_trace"]
    assert out["citations"]


@pytest.mark.asyncio
async def test_rerank_min_score_emptying_hits_escalates_not_clarify() -> None:
    """RERANK_MIN_SCORE wiping context → escalate, never clarify loop."""
    high_bar = DialogueDeps(
        llm=_FakeLLM(label="specific"),
        retrieval=RetrievalService(
            embeddings=_FakeEmbeddings(),
            vectorstore=_FakeVectorStore(
                [{**_OTCHET_HIT, "score": 0.2}]  # below min score
            ),
            rerank_min_score=0.85,
        ),
        grounding=GroundingService(min_citations=1, min_score=0.0),
        quality_email="quality@example.invalid",
    )
    graph = build_dialogue_graph(high_bar)
    out = await graph.ainvoke(
        {
            "user_message": "Кто отвечает за организацию отчётности по проекту?",
            "history": [],
            "clarify_turns": 0,
            "max_clarify_turns": 3,
        }
    )
    assert out["outcome"] == "escalate"
    assert out["escalation_reason"] == "insufficient_citations"
    assert not any(t.startswith("clarify:") for t in out["node_trace"])
