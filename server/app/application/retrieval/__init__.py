"""
ANCHOR: app.application.retrieval
PURPOSE: Hybrid dense+sparse search, RRF, optional rerank, prefer-latest.
Dependencies: embeddings port, vectorstore port, optional llm for rerank
DO:
- Prefer latest effective docs when configured
DONT:
- Return answers — retrieval only yields candidates
"""
