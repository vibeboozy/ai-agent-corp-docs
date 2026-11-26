"""
ANCHOR: app.config
PURPOSE: Settings (pydantic-settings) and DI factories for real adapters.
Dependencies: pydantic-settings, adapters
CRITICAL: Always wire live LLM/embeddings/Qdrant/Docling/Postgres clients.
DO:
- Switch providers by env only — no call-site edits
DONT:
- Hard-code real credentials in code
"""
