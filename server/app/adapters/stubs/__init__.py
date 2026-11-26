"""
ANCHOR: app.adapters.stubs
PURPOSE: Deterministic Stub* implementations — default for local/CI (ANC-STUB-01).
Dependencies: adapter ports
CRITICAL: CI/local must not require live LLM/embeddings/Qdrant/Docling.
DO:
- Return fixtures rich enough for grounded/ambiguous/empty demos (later)
- Selectable only via factories
DONT:
- Bypass grounding because stub text looks nice (ANC-STUB-04)
"""

from __future__ import annotations

from app.adapters.stubs.docling import StubDoclingClient
from app.adapters.stubs.embeddings import StubEmbeddingsClient
from app.adapters.stubs.escalation import StubEscalationNotifier
from app.adapters.stubs.libreoffice import StubLibreOffice
from app.adapters.stubs.llm import StubLLMClient
from app.adapters.stubs.persistence import StubPersistence
from app.adapters.stubs.vectorstore import StubVectorStore

__all__ = [
    "StubDoclingClient",
    "StubEmbeddingsClient",
    "StubEscalationNotifier",
    "StubLibreOffice",
    "StubLLMClient",
    "StubPersistence",
    "StubVectorStore",
]
