"""
ANCHOR: app.application.retrieval
PURPOSE: Hybrid dense+sparse search, RRF, prefer-latest.
Dependencies: embeddings port, vectorstore port
DO:
- Prefer latest effective docs when configured
DONT:
- Return answers — retrieval only yields candidates
"""
