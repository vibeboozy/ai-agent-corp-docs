"""
ANCHOR: tests.application.test_dialogue_graph_module
PURPOSE: Assert dialogue graph module placeholder shape (no live LangGraph run required).
Dependencies: app.application.dialogue.graph
"""

from __future__ import annotations

from app.application.dialogue.graph import compile_placeholder_graph
from app.application.dialogue.state import DialogueState


def test_placeholder_graph_descriptor() -> None:
    desc = compile_placeholder_graph()
    assert desc["state"] is DialogueState
