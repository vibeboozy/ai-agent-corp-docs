"""
ANCHOR: app.application.dialogue.graph
PURPOSE: Compile LangGraph StateGraph for clarify/retrieve/ground/answer/escalate.
Dependencies: langgraph; dialogue.nodes; ports via DI
CRITICAL: Topology is source of truth for clarify/retrieve/ground/answer/escalate (ANC-LG-01).
DO:
- Compile graph with DI-injected node wiring
- Keep topology independent of concrete adapters
DONT:
- Add LangChain RetrievalQA path that skips grounding (ANC-LG-02)
"""

from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from app.application.dialogue.nodes import DialogueDeps, make_nodes
from app.application.dialogue.state import DialogueState


def _route_after_assess(
    state: DialogueState,
) -> Literal["clarify", "retrieve"]:
    """
    specific → retrieve (then ground/answer or escalate).
    underspecified|ambiguous → clarify (no retrieval yet).

    Assess applies prefer_specific_label so role+topic questions reach retrieve
    even when the raw LLM label was timid. Empty retrieval / RERANK_MIN_SCORE
    wiping hits escalates in ground — it must not loop clarify.
    """
    specificity = state.get("specificity") or "underspecified"
    if specificity in ("underspecified", "ambiguous"):
        return "clarify"
    return "retrieve"


def _route_after_clarify(
    state: DialogueState,
) -> Literal["escalate", "__end__"]:
    if state.get("outcome") == "escalate":
        return "escalate"
    return "__end__"


def _route_after_ground(
    state: DialogueState,
) -> Literal["answer", "escalate"]:
    if state.get("grounded"):
        return "answer"
    return "escalate"


def build_dialogue_graph(deps: DialogueDeps) -> Any:
    """Compile the dialogue StateGraph with DI-bound nodes."""
    nodes = make_nodes(deps)
    graph: StateGraph = StateGraph(DialogueState)
    graph.add_node("assess_specificity", nodes["assess_specificity"])
    graph.add_node("clarify", nodes["clarify"])
    graph.add_node("retrieve", nodes["retrieve"])
    graph.add_node("ground", nodes["ground"])
    graph.add_node("answer", nodes["answer"])
    graph.add_node("escalate", nodes["escalate"])

    graph.add_edge(START, "assess_specificity")
    graph.add_conditional_edges(
        "assess_specificity",
        _route_after_assess,
        {"clarify": "clarify", "retrieve": "retrieve"},
    )
    graph.add_conditional_edges(
        "clarify",
        _route_after_clarify,
        {"escalate": "escalate", "__end__": END},
    )
    graph.add_edge("retrieve", "ground")
    graph.add_conditional_edges(
        "ground",
        _route_after_ground,
        {"answer": "answer", "escalate": "escalate"},
    )
    graph.add_edge("answer", END)
    graph.add_edge("escalate", END)
    return graph.compile()


def compile_placeholder_graph() -> dict[str, type]:
    """Backward-compatible descriptor for skeleton tests."""
    return {"state": DialogueState}
