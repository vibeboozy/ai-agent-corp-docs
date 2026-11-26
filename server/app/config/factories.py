"""
ANCHOR: app.config.factories
PURPOSE: DI factory: build port implementations from Settings (stubs by default).
Dependencies: Settings; adapters.*; adapters.stubs.*
DO:
- Construction of Stub*/Http* only here (CS-STUB-04)
DONT:
- Let application services import Stub* or Http*
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.adapters.stubs import (
    StubDoclingClient,
    StubEmbeddingsClient,
    StubEscalationNotifier,
    StubLibreOffice,
    StubLLMClient,
    StubPersistence,
    StubVectorStore,
)
from app.config.settings import Settings


@dataclass
class Container:
    """Port holder — real adapters swapped in when stubs are off (later phases)."""

    llm: Any
    embeddings: Any
    vectorstore: Any
    docling: Any
    libreoffice: Any
    escalation: Any
    persistence: Any


def build_container(settings: Settings) -> Container:
    """Select stub implementations for skeleton phase; real classes TODO."""
    # Real adapters (Http*, Qdrant*, SqlAlchemy*) are wired in later phases.
    _ = settings  # flags consulted when real adapters exist
    return Container(
        llm=StubLLMClient(),
        embeddings=StubEmbeddingsClient(),
        vectorstore=StubVectorStore(),
        docling=StubDoclingClient(),
        libreoffice=StubLibreOffice(),
        escalation=StubEscalationNotifier(),
        persistence=StubPersistence(),
    )
