"""
ANCHOR: app.application.grounding
PURPOSE: Verify assistant claims against retrieved chunks; require citations.
Dependencies: domain ChunkCitation; optional llm port for draft assist
CRITICAL: Final answers MUST be chunk-supported (ANC-GROUND-01/02).
DO:
- Refuse or escalate unsupported claims
DONT:
- Treat LLM draft as sole source of truth
"""
