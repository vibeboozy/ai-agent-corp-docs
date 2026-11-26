"""
ANCHOR: app.domain
PURPOSE: Pure domain models and policies: Appeal, Message, citations — no I/O.
Dependencies: stdlib / pydantic only
DO:
- Keep domain free of FastAPI/httpx/qdrant (CS-DOM-01)
DONT:
- Import adapters or routers
"""
