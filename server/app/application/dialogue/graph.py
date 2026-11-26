"""
ANCHOR: app.application.dialogue.graph
PURPOSE: Compile LangGraph StateGraph for clarify/retrieve/ground/answer/escalate.
Dependencies: langgraph; dialogue.nodes; ports via DI
CRITICAL: Topology is source of truth for clarify/retrieve/ground/answer/escalate (ANC-LG-01).
DO:
- Compile graph with DI-injected node wiring
- Retrieve before clarify so timid classify cannot skip KB hits
- Keep topology independent of concrete adapters
DONT:
- Add LangChain RetrievalQA path that skips grounding (ANC-LG-02)
"""

from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from app.application.dialogue.nodes import DialogueDeps, make_nodes
from app.application.dialogue.specificity import looks_role_topic_specific
from app.application.dialogue.state import DialogueState


def _route_after_retrieve(
    state: DialogueState,
) -> Literal["clarify", "ground"]:
    """
    Retrieve always runs after assess. Then:

    - specific (incl. prefer_specific_label override) OR role+topic heuristic → ground
    - underspecified|ambiguous without role+topic → clarify
    - specific + empty hits escalates inside ground (never clarify-loop)
    """
    specificity = state.get("specificity") or "underspecified"
    msg = state.get("user_message") or ""
    history = list(state.get("history") or [])
    if specificity == "specific" or looks_role_topic_specific(msg, history):
        return "ground"
    if specificity in ("underspecified", "ambiguous"):
        return "clarify"
    return "ground"


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

    # Retrieve-before-clarify: timid classify can no longer skip KB.
    graph.add_edge(START, "assess_specificity")
    graph.add_edge("assess_specificity", "retrieve")
    graph.add_conditional_edges(
        "retrieve",
        _route_after_retrieve,
        {"clarify": "clarify", "ground": "ground"},
    )
    graph.add_conditional_edges(
        "clarify",
        _route_after_clarify,
        {"escalate": "escalate", "__end__": END},
    )
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
