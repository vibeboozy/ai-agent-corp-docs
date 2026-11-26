"""
ANCHOR: app.application.dialogue
PURPOSE: LangGraph dialogue orchestration: clarify | retrieve | ground | answer | escalate.
Dependencies: langgraph_runtime, retrieval, grounding, quality_escalation, llm port, persistence
CRITICAL: Clarify or escalate — never invent (ANC-CLARIFY-01, ANC-ESC-01, ANC-LG-01).
DO:
- Drive behavior via StateGraph edges
- Cap clarify turns via DIALOGUE_MAX_CLARIFY_TURNS
DONT:
- Use LangChain RetrievalQA as primary RAG
- Bypass grounding node
"""
