"""
ANCHOR: app.application.appeals
PURPOSE: Appeal lifecycle: create, list, get, status transitions.
Dependencies: domain, persistence port
DO:
- Persist status transitions with audit
DONT:
- Call LLM or vector store from appeals service
"""
