"""
ANCHOR: tests.application.test_offtopic_refuse
PURPOSE: Off-topic chitchat → refuse; regulation questions still retrieve.
Dependencies: dialogue.offtopic / graph routing / make_nodes
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.application.dialogue import graph as graph_mod
from app.application.dialogue.graph import build_dialogue_graph
from app.application.dialogue.nodes import DialogueDeps, make_nodes
from app.application.dialogue.offtopic import OFF_TOPIC_REFUSAL_RU, is_off_topic
from app.application.grounding.service import GroundingService
from app.application.retrieval.service import RetrievalService


def test_is_off_topic_time_and_weather() -> None:
    assert is_off_topic("Сколько времени?")
    assert is_off_topic("Какая погода?")
    assert not is_off_topic("Кто отвечает за планирование поставок?")
    assert not is_off_topic("Сколько времени отводится на согласование договора?")


def test_route_after_assess_refuse() -> None:
    assert graph_mod._route_after_assess({"specificity": "off_topic"}) == "refuse"
    assert graph_mod._route_after_assess({"specificity": "specific"}) == "retrieve"


@pytest.mark.asyncio
async def test_graph_refuses_off_topic_without_retrieve() -> None:
    embeddings = AsyncMock()
    embeddings.embed_dense = AsyncMock(return_value=[[0.1]])
    embeddings.embed_sparse = AsyncMock(return_value=[{"q": 1.0}])
    vectorstore = AsyncMock()
    vectorstore.search = AsyncMock(return_value=[])
    llm = AsyncMock()
    llm.classify_specificity = AsyncMock(return_value="specific")
    llm.complete = AsyncMock(return_value="should-not-run")
    deps = DialogueDeps(
        llm=llm,
        retrieval=RetrievalService(embeddings=embeddings, vectorstore=vectorstore),
        grounding=GroundingService(),
        quality_email="q@example.invalid",
    )
    graph = build_dialogue_graph(deps)
    out = await graph.ainvoke(
        {
            "user_message": "Сколько времени?",
            "history": [],
            "clarify_turns": 0,
            "max_clarify_turns": 3,
            "node_trace": [],
        }
    )
    assert out["outcome"] == "refuse"
    assert OFF_TOPIC_REFUSAL_RU in (out.get("draft_answer") or "")
    vectorstore.search.assert_not_awaited()
    llm.classify_specificity.assert_not_awaited()


@pytest.mark.asyncio
async def test_assess_node_marks_off_topic() -> None:
    deps = DialogueDeps(
        llm=AsyncMock(),
        retrieval=RetrievalService(
            embeddings=AsyncMock(),
            vectorstore=AsyncMock(),
        ),
        grounding=GroundingService(),
        quality_email="q@example.invalid",
    )
    nodes = make_nodes(deps)
    assessed = await nodes["assess_specificity"](
        {"user_message": "Сколько времени", "history": [], "node_trace": []}
    )
    assert assessed["specificity"] == "off_topic"
