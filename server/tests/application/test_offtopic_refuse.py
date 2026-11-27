"""
ANCHOR: tests.application.test_offtopic_refuse
PURPOSE: Off-topic chitchat → refuse; regs + ALLOWED_TOPICS still retrieve.
Dependencies: dialogue.offtopic / graph routing / make_nodes / allowed_topics
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.application.dialogue import graph as graph_mod
from app.application.dialogue.graph import build_dialogue_graph
from app.application.dialogue.nodes import DialogueDeps, make_nodes
from app.application.dialogue.offtopic import (
    OFF_TOPIC_REFUSAL_RU,
    is_off_topic,
    is_supported_domain,
)
from app.application.grounding.service import GroundingService
from app.application.retrieval.service import RetrievalService
from app.domain.allowed_topics import resolve_allowed_topics


def test_is_off_topic_time_and_weather() -> None:
    assert is_off_topic("Сколько времени?")
    assert is_off_topic("Какая погода?")
    assert not is_off_topic("Кто отвечает за планирование поставок?")
    assert not is_off_topic("Сколько времени отводится на согласование договора?")


def test_allowed_topics_allow_constitution_refuse_weather() -> None:
    topics = resolve_allowed_topics(
        "Конституция РФ=основной закон РФ;Трудовой кодекс РФ"
    )
    assert is_supported_domain("Что говорит Конституция РФ о правах?", topics)
    assert not is_off_topic(
        "Что говорит Конституция РФ о правах?", allowed_topics=topics
    )
    assert not is_off_topic(
        "Какой срок предупреждения по Трудовому кодексу РФ?", allowed_topics=topics
    )
    # Weather / time stay refused even with extras configured.
    assert is_off_topic("Какая погода?", allowed_topics=topics)
    assert is_off_topic("Сколько времени?", allowed_topics=topics)
    assert not is_supported_domain("Какая погода?", topics)


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
async def test_graph_allows_configured_topic_and_retrieves() -> None:
    """ALLOWED_TOPICS question must pass the retrieve gate (not refuse)."""
    topics = resolve_allowed_topics("Конституция РФ")
    embeddings = AsyncMock()
    embeddings.embed_dense = AsyncMock(return_value=[[0.1]])
    embeddings.embed_sparse = AsyncMock(return_value=[{"q": 1.0}])
    vectorstore = AsyncMock()
    vectorstore.search = AsyncMock(
        return_value=[
            {
                "document_id": "constitution-rf",
                "chunk_id": "c1",
                "document_title": "Конституция РФ",
                "text": "Статья 29. Каждому гарантируется свобода мысли и слова.",
                "score": 0.9,
                "locator": "Конституция РФ, ст. 29",
            }
        ]
    )
    llm = AsyncMock()
    # Timid classifier may still say off_topic; domain gate must override.
    llm.classify_specificity = AsyncMock(return_value="off_topic")
    llm.complete = AsyncMock(
        return_value="Каждому гарантируется свобода мысли и слова [0]."
    )
    deps = DialogueDeps(
        llm=llm,
        retrieval=RetrievalService(embeddings=embeddings, vectorstore=vectorstore),
        grounding=GroundingService(),
        quality_email="q@example.invalid",
        allowed_topics=topics,
    )
    graph = build_dialogue_graph(deps)
    out = await graph.ainvoke(
        {
            "user_message": "Что говорит Конституция РФ о свободе слова?",
            "history": [],
            "clarify_turns": 0,
            "max_clarify_turns": 3,
            "node_trace": [],
        }
    )
    assert out["outcome"] != "refuse"
    assert out.get("specificity") != "off_topic"
    vectorstore.search.assert_awaited()
    llm.classify_specificity.assert_awaited()


@pytest.mark.asyncio
async def test_refuse_message_includes_configured_topics() -> None:
    topics = resolve_allowed_topics("Конституция РФ;Трудовой кодекс РФ")
    deps = DialogueDeps(
        llm=AsyncMock(),
        retrieval=RetrievalService(
            embeddings=AsyncMock(),
            vectorstore=AsyncMock(),
        ),
        grounding=GroundingService(),
        quality_email="q@example.invalid",
        allowed_topics=topics,
    )
    nodes = make_nodes(deps)
    refused = await nodes["refuse"]({"user_message": "Какая погода?", "node_trace": []})
    text = refused.get("draft_answer") or ""
    assert "Конституция РФ" in text
    assert "Трудовой кодекс РФ" in text
    assert refused["outcome"] == "refuse"


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


@pytest.mark.asyncio
async def test_assess_overrides_llm_off_topic_for_allowed_topic() -> None:
    topics = resolve_allowed_topics("Трудовой кодекс РФ")
    llm = AsyncMock()
    llm.classify_specificity = AsyncMock(return_value="off_topic")
    deps = DialogueDeps(
        llm=llm,
        retrieval=RetrievalService(
            embeddings=AsyncMock(),
            vectorstore=AsyncMock(),
        ),
        grounding=GroundingService(),
        quality_email="q@example.invalid",
        allowed_topics=topics,
    )
    nodes = make_nodes(deps)
    assessed = await nodes["assess_specificity"](
        {
            "user_message": "Какой испытательный срок по Трудовому кодексу РФ?",
            "history": [],
            "node_trace": [],
        }
    )
    assert assessed["specificity"] != "off_topic"
    assert assessed["raw_specificity"] == "off_topic"
