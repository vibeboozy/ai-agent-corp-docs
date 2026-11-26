"""
ANCHOR: app.application.retrieval
PURPOSE: Hybrid dense+sparse search, optional LLM rerank, prefer-latest.
Dependencies: embeddings port, vectorstore port, optional LLMClient
DO:
- Prefer latest effective docs when configured
- Expose retrieve_with_meta (latency + rerank scores) for dialogue audit
DONT:
- Return answers — retrieval only yields candidates
"""
