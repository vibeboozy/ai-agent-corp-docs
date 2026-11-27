"""
ANCHOR: app.application.ingest.service
PURPOSE: Ingest text/docs into vectorstore via Docling + embeddings.
Dependencies: docling, libreoffice, embeddings, vectorstore, persistence, embed_limits
DO:
- Update document/chunk metadata in persistence
- On Docling failure for short officer text, chunk locally then embed→Qdrant
- Split oversized chunk text before dense/sparse embed (embeddings ~8000 char cap)
DONT:
- Require Docling for the learn / ingest_text path
- Skip provenance for learned officer text
- Send >MAX_EMBED_CHARS text to embeddings (one oversize item 400s the batch)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.adapters.docling.port import DoclingClient
from app.adapters.embeddings.port import EmbeddingsClient
from app.adapters.persistence.port import Persistence
from app.adapters.vectorstore.port import VectorStore
from app.application.ingest.embed_limits import ensure_embeddable_chunks
from app.domain.glossary import AbbreviationGlossary

logger = logging.getLogger(__name__)


def _local_text_chunks(*, text: str, job_id: str) -> list[dict[str, Any]]:
    """Single/simple local chunk for short officer answers when Docling is unavailable."""
    return [{"chunk_id": f"c-{job_id[:8]}", "text": text}]


class IngestService:
    def __init__(
        self,
        *,
        docling: DoclingClient,
        embeddings: EmbeddingsClient,
        vectorstore: VectorStore,
        persistence: Persistence,
        glossary: AbbreviationGlossary | None = None,
    ) -> None:
        self._docling = docling
        self._embeddings = embeddings
        self._vectorstore = vectorstore
        self._persistence = persistence
        self._glossary = glossary

    async def _chunks_for_text(self, *, text: str, job_id: str) -> tuple[list[dict[str, Any]], bool]:
        """
        Prefer Docling convert; on any failure (or empty chunks) fall back to local chunks.

        Returns (chunks, used_local_fallback).
        """
        try:
            converted = await self._docling.convert(text=text)
            chunks = list(converted.get("chunks") or [])
            if chunks:
                return chunks, False
            logger.info(
                "Docling returned no chunks for learn ingest; using local single chunk job_id=%s",
                job_id,
            )
        except Exception as exc:
            logger.warning(
                "Docling convert failed for learn ingest; using local chunks job_id=%s err=%s",
                job_id,
                exc,
            )
        return _local_text_chunks(text=text, job_id=job_id), True

    def _enrich_chunks(self, raw_chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Expand abbreviations into chunk TEXT before embed so dense/sparse see them."""
        enriched: list[dict[str, Any]] = []
        for chunk in raw_chunks:
            body = str(chunk.get("text") or "")
            if self._glossary is not None:
                body = self._glossary.enrich_text(body)
            enriched.append({**chunk, "text": body})
        return enriched

    async def _embed_and_upsert(
        self,
        *,
        chunks: list[dict[str, Any]],
        document_id: str,
        document_title: str,
        source: str,
        keywords: list[str] | None,
        base_metadata: dict[str, Any] | None,
        used_local_fallback: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Glossary-enrich → clamp to embed limit → dense/sparse embed → Qdrant upsert.

        Shared by learn ingest_text and CLI ingest_file so both paths are guarded.
        """
        enriched = self._enrich_chunks(chunks)
        # Cap before embed: HybridChunker merges / Cyrillic whitespace-tokens can
        # exceed the embeddings API ~8000 char limit and 400 the whole batch.
        embeddable = ensure_embeddable_chunks(enriched)
        texts = [str(c.get("text") or "") for c in embeddable]
        vectors = await self._embeddings.embed_dense(texts)
        sparse_maps = await self._embeddings.embed_sparse(texts)
        upserts: list[dict[str, Any]] = []
        for idx, chunk in enumerate(embeddable):
            chunk_id = chunk.get("chunk_id") or f"c-{uuid4().hex[:8]}"
            dense = vectors[idx] if idx < len(vectors) else None
            sparse = sparse_maps[idx] if idx < len(sparse_maps) else None
            meta = {
                **(base_metadata or {}),
                **(chunk.get("metadata") or {}),
            }
            if used_local_fallback:
                meta["chunking"] = "local_fallback"
            if chunk.get("section_title"):
                meta["section_title"] = chunk["section_title"]
            if self._glossary is not None:
                meta = self._glossary.enrich_metadata(str(chunk["text"]), meta)
            upserts.append(
                {
                    "document_id": document_id,
                    "chunk_id": chunk_id,
                    "text": chunk["text"],
                    "document_title": document_title,
                    "keywords": keywords or [],
                    "source": source,
                    "locator": chunk.get("locator") or chunk.get("section_title"),
                    "dense_vector": dense,
                    "sparse_vector": sparse,
                    "metadata": meta,
                }
            )
        await self._vectorstore.upsert(upserts)
        return upserts

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
        raw_chunks, used_local_fallback = await self._chunks_for_text(text=text, job_id=job_id)
        upserts = await self._embed_and_upsert(
            chunks=raw_chunks,
            document_id=doc_id,
            document_title=document_title,
            source="learned",
            keywords=keywords,
            base_metadata={**(metadata or {}), "ingest_job_id": job_id},
            used_local_fallback=used_local_fallback,
        )
        await self._persistence.add_audit_event(
            appeal_id=None,
            event_type="ingest_completed",
            payload={
                "ingest_job_id": job_id,
                "document_id": doc_id,
                "chunks": len(upserts),
                "chunking": "local_fallback" if used_local_fallback else "docling",
            },
        )
        return {
            "ingest_job_id": job_id,
            "document_id": doc_id,
            "chunks": len(upserts),
            "chunking": "local_fallback" if used_local_fallback else "docling",
        }

    async def ingest_file(
        self,
        *,
        source_path: str | Path,
        document_title: str | None = None,
        document_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Convert a local Docling-supported file and upsert embeddable chunks.

        Used by CLI ``ingest-file`` so file ingest shares the same embed-limit
        guard as learn / officer-reply ingest_text.
        """
        src = Path(source_path)
        if not src.is_file():
            raise FileNotFoundError(f"Ingest source not found: {src}")
        job_id = str(uuid4())
        converted = await self._docling.convert(source_path=str(src.resolve()))
        chunks = list(converted.get("chunks") or [])
        if not chunks:
            raise ValueError("Docling returned no chunks")
        title = document_title or src.stem
        doc_id = document_id or f"doc-{src.stem}"
        upserts = await self._embed_and_upsert(
            chunks=chunks,
            document_id=doc_id,
            document_title=title,
            source="ingest",
            keywords=None,
            base_metadata={"ingest_job_id": job_id, "source_path": str(src)},
            used_local_fallback=False,
        )
        await self._persistence.add_audit_event(
            appeal_id=None,
            event_type="ingest_completed",
            payload={
                "ingest_job_id": job_id,
                "document_id": doc_id,
                "chunks": len(upserts),
                "chunking": "docling",
                "source_path": str(src),
            },
        )
        return {
            "ingest_job_id": job_id,
            "document_id": doc_id,
            "chunks": len(upserts),
            "chunking": "docling",
            "document_title": title,
            "source_path": str(src),
        }
