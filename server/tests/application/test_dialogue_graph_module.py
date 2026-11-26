"""
ANCHOR: tests.application.test_dialogue_graph_module
PURPOSE: Assert dialogue graph module shape and LangGraph compile with stubs.
Dependencies: app.application.dialogue.graph
"""

from __future__ import annotations

from app.adapters.stubs.embeddings import StubEmbeddingsClient
from app.adapters.stubs.llm import StubLLMClient
from app.adapters.stubs.vectorstore import StubVectorStore
from app.application.dialogue.graph import build_dialogue_graph, compile_placeholder_graph
from app.application.dialogue.nodes import DialogueDeps
from app.application.dialogue.state import DialogueState
from app.application.grounding.service import GroundingService
from app.application.retrieval.service import RetrievalService


def test_placeholder_graph_descriptor() -> None:
    desc = compile_placeholder_graph()
    assert desc["state"] is DialogueState


def test_langgraph_compiles_with_stub_nodes() -> None:
    deps = DialogueDeps(
        llm=StubLLMClient(),
        retrieval=RetrievalService(
            embeddings=StubEmbeddingsClient(),
            vectorstore=StubVectorStore(),
        ),
        grounding=GroundingService(),
        quality_email="quality@example.invalid",
    )
    compiled = build_dialogue_graph(deps)
    assert hasattr(compiled, "ainvoke")
