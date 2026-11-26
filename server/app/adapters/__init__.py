"""
ANCHOR: app.adapters
PURPOSE: Outbound ports and implementations (LLM, embeddings, Qdrant, Docling, persistence, escalation).
Dependencies: domain types; httpx/qdrant/sqlalchemy in concrete adapters only
DO:
- Protocol/ABC + real Http*/Qdrant*/SqlAlchemy*
DONT:
- Scatter raw HTTP in application services
"""
