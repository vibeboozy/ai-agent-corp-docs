"""
ANCHOR: app.application.ingest.service
PURPOSE: Ingest text/docs into vectorstore via Docling + embeddings (stub OK).
Dependencies: docling, libreoffice, embeddings, vectorstore, persistence
DO:
- Update document/chunk metadata in persistence
DONT:
- Skip provenance for learned officer text
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.adapters.docling.port import DoclingClient
from app.adapters.embeddings.port import EmbeddingsClient
from app.adapters.persistence.port import Persistence
from app.adapters.vectorstore.port import VectorStore


class IngestService:
    def __init__(
        self,
        *,
        docling: DoclingClient,
        embeddings: EmbeddingsClient,
        vectorstore: VectorStore,
        persistence: Persistence,
    ) -> None:
        self._docling = docling
        self._embeddings = embeddings
        self._vectorstore = vectorstore
        self._persistence = persistence

    async def ingest_text(
        self,
        *,
        text: str,
        document_id: str | None = None,
        document_title: str = "Canonical officer answer",
        keywords: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        job_id = str(uuid4())
        doc_id = document_id or f"learned-{job_id[:8]}"
        converted = await self._docling.convert(text=text)
        raw_chunks = converted.get("chunks") or [{"chunk_id": f"c-{job_id[:8]}", "text": text}]
        # Ensure embeddings path is exercised (even if stub vectorstore ignores vectors).
        await self._embeddings.embed_dense([c["text"] for c in raw_chunks])
        upserts = []
        for chunk in raw_chunks:
            upserts.append(
                {
                    "document_id": doc_id,
                    "chunk_id": chunk.get("chunk_id") or f"c-{uuid4().hex[:8]}",
                    "text": chunk["text"],
                    "document_title": document_title,
                    "keywords": keywords or [],
                    "source": "learned",
                    "metadata": {
                        **(metadata or {}),
                        "ingest_job_id": job_id,
                    },
                }
            )
        await self._vectorstore.upsert(upserts)
        await self._persistence.add_audit_event(
            appeal_id=None,
            event_type="ingest_completed",
            payload={"ingest_job_id": job_id, "document_id": doc_id, "chunks": len(upserts)},
        )
        return {"ingest_job_id": job_id, "document_id": doc_id, "chunks": len(upserts)}
