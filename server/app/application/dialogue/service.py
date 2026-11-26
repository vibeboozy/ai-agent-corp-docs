"""
ANCHOR: app.application.dialogue.service
PURPOSE: Service skeleton for dialogue (NotImplemented).
Dependencies: langgraph_runtime, retrieval, grounding, quality_escalation, llm port, persistence
CRITICAL: Clarify or escalate — never invent (ANC-CLARIFY-01, ANC-ESC-01, ANC-LG-01).
DO:
- Drive behavior via StateGraph edges
- Cap clarify turns via DIALOGUE_MAX_CLARIFY_TURNS
DONT:
- Use LangChain RetrievalQA as primary RAG
- Bypass grounding node
"""

from __future__ import annotations


class DialogueService:
    """Placeholder application service — implement in later phases."""

    async def run(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise NotImplementedError("dialogue service not implemented")
