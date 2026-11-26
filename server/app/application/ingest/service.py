"""
ANCHOR: app.application.ingest.service
PURPOSE: Ingest text/docs into vectorstore via Docling + embeddings.
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
        texts = [c["text"] for c in raw_chunks]
        vectors = await self._embeddings.embed_dense(texts)
        sparse_maps = await self._embeddings.embed_sparse(texts)
        upserts = []
        for idx, chunk in enumerate(raw_chunks):
            chunk_id = chunk.get("chunk_id") or f"c-{uuid4().hex[:8]}"
            dense = vectors[idx] if idx < len(vectors) else None
            sparse = sparse_maps[idx] if idx < len(sparse_maps) else None
            upserts.append(
                {
                    "document_id": doc_id,
                    "chunk_id": chunk_id,
                    "text": chunk["text"],
                    "document_title": document_title,
                    "keywords": keywords or [],
                    "source": "learned",
                    "dense_vector": dense,
                    "sparse_vector": sparse,
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
