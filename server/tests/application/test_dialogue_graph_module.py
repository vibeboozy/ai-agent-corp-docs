"""
ANCHOR: tests.application.test_dialogue_graph_module
PURPOSE: Assert dialogue graph module shape and LangGraph compile with mocked ports.
Dependencies: app.application.dialogue.graph
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.application.dialogue.graph import build_dialogue_graph, compile_placeholder_graph
from app.application.dialogue.nodes import DialogueDeps
from app.application.dialogue.state import DialogueState
from app.application.grounding.service import GroundingService
from app.application.retrieval.service import RetrievalService


def test_placeholder_graph_descriptor() -> None:
    desc = compile_placeholder_graph()
    assert desc["state"] is DialogueState


def test_langgraph_compiles_with_mocked_ports() -> None:
    embeddings = MagicMock()
    embeddings.embed_dense = AsyncMock(return_value=[[0.1, 0.2]])
    embeddings.embed_sparse = AsyncMock(return_value=[{"x": 1.0}])
    vectorstore = MagicMock()
    vectorstore.search = AsyncMock(return_value=[])
    llm = MagicMock()
    llm.complete = AsyncMock(return_value="ok")
    llm.classify_specificity = AsyncMock(return_value="specific")

    deps = DialogueDeps(
        llm=llm,
        retrieval=RetrievalService(embeddings=embeddings, vectorstore=vectorstore),
        grounding=GroundingService(),
        quality_email="quality@example.invalid",
    )
    compiled = build_dialogue_graph(deps)
    assert hasattr(compiled, "ainvoke")
