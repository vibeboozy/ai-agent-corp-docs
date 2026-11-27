"""
ANCHOR: tests.application.test_ingest_docling_fallback
PURPOSE: Learn ingest survives Docling-down via local single/simple chunks → embed → Qdrant.
Dependencies: IngestService + Fake ports
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.application.ingest.service import IngestService
from app.domain.errors import AppError, UpstreamTimeoutError


class _DownDocling:
    def __init__(self, exc: BaseException) -> None:
        self._exc = exc
        self.calls = 0

    async def convert(self, *, source_path: str | None = None, text: str | None = None) -> dict:
        _ = (source_path, text)
        self.calls += 1
        raise self._exc


class _EmptyDocling:
    async def convert(self, *, source_path: str | None = None, text: str | None = None) -> dict:
        _ = (source_path, text)
        return {"chunks": []}


def _build_service(*, docling: Any) -> tuple[IngestService, list[dict[str, Any]], AsyncMock, AsyncMock]:
    embeddings = AsyncMock()
    embeddings.embed_dense = AsyncMock(side_effect=lambda texts: [[0.1, 0.2] for _ in texts])
    embeddings.embed_sparse = AsyncMock(side_effect=lambda texts: [{"tok": 1.0} for _ in texts])

    upserted: list[dict[str, Any]] = []

    async def _upsert(chunks: list[dict[str, Any]]) -> None:
        upserted.extend(chunks)

    vectorstore = AsyncMock()
    vectorstore.upsert = AsyncMock(side_effect=_upsert)
    persistence = AsyncMock()
    persistence.add_audit_event = AsyncMock()

    svc = IngestService(
        docling=docling,
        embeddings=embeddings,
        vectorstore=vectorstore,
        persistence=persistence,
    )
    return svc, upserted, embeddings, persistence


@pytest.mark.asyncio
async def test_ingest_text_falls_back_when_docling_upstream_error() -> None:
    docling = _DownDocling(AppError("Docling upstream error", code="UPSTREAM_ERROR"))
    svc, upserted, embeddings, persistence = _build_service(docling=docling)

    officer = "Цвет логотипа — Pantone 286 C по брендбуку."
    result = await svc.ingest_text(
        text=officer,
        document_title="Канонический ответ офицера качества",
        keywords=["логотип"],
        metadata={"appeal_id": "a1"},
    )

    assert docling.calls == 1
    assert result["chunks"] == 1
    assert result["chunking"] == "local_fallback"
    assert result["document_id"].startswith("learned-")

    embeddings.embed_dense.assert_awaited_once()
    embeddings.embed_sparse.assert_awaited_once()
    dense_texts = embeddings.embed_dense.await_args.args[0]
    assert dense_texts == [officer]

    assert len(upserted) == 1
    point = upserted[0]
    assert point["text"] == officer
    assert point["source"] == "learned"
    assert point["document_title"] == "Канонический ответ офицера качества"
    assert point["keywords"] == ["логотип"]
    assert point["dense_vector"] == [0.1, 0.2]
    assert point["sparse_vector"] == {"tok": 1.0}
    assert point["metadata"]["chunking"] == "local_fallback"
    assert point["metadata"]["appeal_id"] == "a1"
    assert point["chunk_id"].startswith("c-")

    persistence.add_audit_event.assert_awaited_once()
    audit_kw = persistence.add_audit_event.await_args.kwargs
    assert audit_kw["event_type"] == "ingest_completed"
    assert audit_kw["payload"]["chunking"] == "local_fallback"
    assert audit_kw["payload"]["chunks"] == 1


@pytest.mark.asyncio
async def test_ingest_text_falls_back_when_docling_times_out() -> None:
    docling = _DownDocling(UpstreamTimeoutError("Docling request timed out"))
    svc, upserted, embeddings, _persistence = _build_service(docling=docling)

    result = await svc.ingest_text(text="Короткий канонический ответ.")

    assert result["chunking"] == "local_fallback"
    assert upserted[0]["text"] == "Короткий канонический ответ."
    embeddings.embed_dense.assert_awaited_once()


@pytest.mark.asyncio
async def test_ingest_text_falls_back_when_docling_returns_empty_chunks() -> None:
    svc, upserted, embeddings, _persistence = _build_service(docling=_EmptyDocling())

    result = await svc.ingest_text(text="Пустой Docling → один локальный чанк.")

    assert result["chunking"] == "local_fallback"
    assert len(upserted) == 1
    assert upserted[0]["text"] == "Пустой Docling → один локальный чанк."
    embeddings.embed_dense.assert_awaited_once()


@pytest.mark.asyncio
async def test_ingest_text_uses_docling_chunks_when_available() -> None:
    class _OkDocling:
        async def convert(self, *, source_path: str | None = None, text: str | None = None) -> dict:
            _ = source_path
            return {
                "chunks": [
                    {"chunk_id": "d1", "text": text or "", "section_title": "§1"},
                ]
            }

    svc, upserted, _embeddings, persistence = _build_service(docling=_OkDocling())
    result = await svc.ingest_text(text="Ответ из Docling.")

    assert result["chunking"] == "docling"
    assert upserted[0]["chunk_id"] == "d1"
    assert upserted[0]["locator"] == "§1"
    assert "chunking" not in upserted[0]["metadata"]
    assert persistence.add_audit_event.await_args.kwargs["payload"]["chunking"] == "docling"
