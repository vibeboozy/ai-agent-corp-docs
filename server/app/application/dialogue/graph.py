"""
ANCHOR: app.application.dialogue.graph
PURPOSE: Compile LangGraph StateGraph placeholder; optional checkpoint by appeal_id.
Dependencies: langgraph; dialogue.nodes; ports via DI
CRITICAL: Topology is source of truth for clarify/retrieve/ground/answer/escalate (ANC-LG-01).
DO:
- Compile graph with stub no-op wiring later
- Keep offline-runnable with stubs
DONT:
- Add LangChain RetrievalQA path that skips grounding (ANC-LG-02)
"""

from __future__ import annotations

from typing import Any

from app.application.dialogue.state import DialogueState


def build_dialogue_graph(*_args: Any, **_kwargs: Any) -> Any:
    """
    Placeholder for StateGraph compilation.

    Later phases: define nodes/edges with langgraph; inject ports via closures/DI.
    Skeleton intentionally does not import langgraph at module import time until
    dependencies are installed and nodes are implemented.
    """
    raise NotImplementedError(
        "Dialogue StateGraph not implemented — see project_context.md §2.1 / phase 3"
    )


def compile_placeholder_graph() -> dict[str, type]:
    """Return a minimal descriptor so tests can assert graph module shape."""
    return {"state": DialogueState}
