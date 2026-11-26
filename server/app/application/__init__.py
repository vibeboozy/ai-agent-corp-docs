"""
ANCHOR: app.application
PURPOSE: Application services and LangGraph orchestration (use cases).
Dependencies: domain, adapters ports via DI
DO:
- Own dialogue/grounding/learning policies
DONT:
- Import FastAPI routers
- Import Stub* or Http* concrete adapters
"""
