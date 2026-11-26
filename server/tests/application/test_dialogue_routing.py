"""
ANCHOR: tests.application.test_dialogue_routing
PURPOSE: Focused offline tests — LangGraph route helpers, node set, node outcomes.
Dependencies: dialogue.graph / dialogue.nodes (no live URLs)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.application.dialogue import graph as graph_mod
from app.application.dialogue.graph import build_dialogue_graph
from app.application.dialogue.nodes import DialogueDeps, make_nodes
from app.application.grounding.service import GroundingService
from app.application.retrieval.service import RetrievalService


def test_route_after_retrieve_clarify_vs_ground() -> None:
    assert (
        graph_mod._route_after_retrieve({"specificity": "underspecified", "user_message": "?"})
        == "clarify"
    )
    assert (
        graph_mod._route_after_retrieve(
            {"specificity": "ambiguous", "user_message": "Кто подписывает договоры?"}
        )
        == "clarify"
    )
    assert (
        graph_mod._route_after_retrieve(
            {
                "specificity": "specific",
                "user_message": "Кто отвечает за организацию отчётности по проекту?",
            }
        )
        == "ground"
    )
    # Timid label but role+topic → ground despite underspecified.
    assert (
        graph_mod._route_after_retrieve(
            {
                "specificity": "underspecified",
                "user_message": "Кто отвечает за организацию отчётности по проекту?",
            }
        )
        == "ground"
    )
    assert graph_mod._route_after_retrieve({}) == "clarify"


def test_route_after_clarify_end_or_escalate() -> None:
    assert graph_mod._route_after_clarify({"outcome": "clarify"}) == "__end__"
    assert graph_mod._route_after_clarify({"outcome": "escalate"}) == "escalate"
    assert graph_mod._route_after_clarify({}) == "__end__"


def test_route_after_ground_answer_or_escalate() -> None:
    assert graph_mod._route_after_ground({"grounded": True}) == "answer"
    assert graph_mod._route_after_ground({"grounded": False}) == "escalate"
    assert graph_mod._route_after_ground({}) == "escalate"


def _minimal_deps() -> DialogueDeps:
    embeddings = AsyncMock()
    embeddings.embed_dense = AsyncMock(return_value=[[0.1]])
    embeddings.embed_sparse = AsyncMock(return_value=[{"q": 1.0}])
    vectorstore = AsyncMock()
    vectorstore.search = AsyncMock(return_value=[])
    llm = AsyncMock()
    llm.classify_specificity = AsyncMock(return_value="specific")
    llm.complete = AsyncMock(return_value="draft")
    return DialogueDeps(
        llm=llm,
        retrieval=RetrievalService(embeddings=embeddings, vectorstore=vectorstore),
        grounding=GroundingService(),
        quality_email="quality@example.invalid",
    )


def test_compiled_graph_exposes_expected_nodes() -> None:
    compiled = build_dialogue_graph(_minimal_deps())
    # LangGraph CompiledStateGraph keeps node names in .nodes
    names = set(getattr(compiled, "nodes", {}).keys())
    expected = {
        "assess_specificity",
        "clarify",
        "retrieve",
        "ground",
        "answer",
        "escalate",
    }
    assert expected.issubset(names)


@pytest.mark.asyncio
async def test_make_nodes_assess_and_clarify() -> None:
    llm = AsyncMock()
    llm.classify_specificity = AsyncMock(return_value="ambiguous")
    llm.complete = AsyncMock(
        return_value="Уточните: договоры на закупку или с подрядчиками?"
    )
    deps = DialogueDeps(
        llm=llm,
        retrieval=RetrievalService(
            embeddings=AsyncMock(
                embed_dense=AsyncMock(return_value=[[0.1]]),
                embed_sparse=AsyncMock(return_value=[{"x": 1.0}]),
            ),
            vectorstore=AsyncMock(search=AsyncMock(return_value=[])),
        ),
        grounding=GroundingService(),
        quality_email="q@example.invalid",
    )
    nodes = make_nodes(deps)
    assessed = await nodes["assess_specificity"](
        {"user_message": "Кто подписывает?", "history": []}
    )
    assert assessed["specificity"] == "ambiguous"
    assert assessed["raw_specificity"] == "ambiguous"
    assert "assess:ambiguous(raw:ambiguous)" in assessed["node_trace"][-1]

    clarified = await nodes["clarify"](
        {**assessed, "clarify_turns": 0, "max_clarify_turns": 3}
    )
    assert clarified["outcome"] == "clarify"
    assert "закупк" in clarified["clarification_text"].lower()
    llm.complete.assert_awaited()


@pytest.mark.asyncio
async def test_make_nodes_ground_ok_and_fail() -> None:
    hits: list[dict[str, Any]] = [
        {
            "document_id": "d1",
            "chunk_id": "c1",
            "text": "Директор по закупкам подписывает договоры.",
            "score": 0.95,
            "document_title": "Регламент",
        }
    ]
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value="ignored-draft")
    deps = DialogueDeps(
        llm=llm,
        retrieval=RetrievalService(
            embeddings=AsyncMock(
                embed_dense=AsyncMock(return_value=[[0.1]]),
                embed_sparse=AsyncMock(return_value=[{"x": 1.0}]),
            ),
            vectorstore=AsyncMock(search=AsyncMock(return_value=hits)),
        ),
        grounding=GroundingService(min_citations=1),
        quality_email="q@example.invalid",
    )
    nodes = make_nodes(deps)

    ok = await nodes["ground"](
        {"user_message": "q", "candidates": hits, "node_trace": []}
    )
    assert ok["outcome"] == "answer"
    assert ok["grounded"] is True
    assert ok["citations"]

    fail = await nodes["ground"](
        {"user_message": "q", "candidates": [], "node_trace": []}
    )
    assert fail["outcome"] == "escalate"
    assert fail["grounded"] is False
