"""
ANCHOR: tests.application.test_ingest_embed_limits
PURPOSE: Oversized HybridChunker / local chunks are split before dense embed.
Dependencies: embed_limits, IngestService + Fake ports
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.application.ingest.embed_limits import (
    MAX_EMBED_CHARS,
    ensure_embeddable_chunks,
)
from app.application.ingest.service import IngestService


def test_ensure_embeddable_chunks_passes_short_through() -> None:
    chunks = [{"chunk_id": "a", "text": "короткий текст", "section_title": "1."}]
    out = ensure_embeddable_chunks(chunks)
    assert out == chunks


def test_ensure_embeddable_chunks_splits_oversized() -> None:
    # Cyrillic-ish payload well above the embeddings ~8000 char hard limit.
    body = ("регулирование " * 800).strip()  # ~11200 chars
    assert len(body) > MAX_EMBED_CHARS
    chunks = [{"chunk_id": "big", "text": body, "locator": "§7"}]
    out = ensure_embeddable_chunks(chunks, max_chars=MAX_EMBED_CHARS)
    assert len(out) >= 2
    assert all(len(c["text"]) <= MAX_EMBED_CHARS for c in out)
    assert out[0]["chunk_id"] == "big"
    assert out[1]["chunk_id"] == "big-p1"
    assert "".join(c["text"] for c in out).replace(" ", "") == body.replace(" ", "")
    assert out[0]["metadata"]["embed_split"] is True
    assert out[0]["metadata"]["embed_original_chars"] == len(body)
    assert out[0]["locator"] == "§7"


def test_ensure_embeddable_hard_cuts_pathological_run() -> None:
    body = "я" * (MAX_EMBED_CHARS + 500)
    out = ensure_embeddable_chunks([{"chunk_id": "x", "text": body}], max_chars=MAX_EMBED_CHARS)
    assert len(out) >= 2
    assert all(len(c["text"]) <= MAX_EMBED_CHARS for c in out)


@pytest.mark.asyncio
async def test_ingest_text_splits_oversized_before_embed() -> None:
    huge = ("абзац регламента " * 600).strip()
    assert len(huge) > MAX_EMBED_CHARS

    class _OkDocling:
        async def convert(self, *, source_path: str | None = None, text: str | None = None) -> dict:
            _ = source_path
            return {"chunks": [{"chunk_id": "d1", "text": text or "", "section_title": "§1"}]}

    embeddings = AsyncMock()
    captured: dict[str, Any] = {}

    async def _dense(texts: list[str]) -> list[list[float]]:
        captured["dense"] = list(texts)
        return [[0.1, 0.2] for _ in texts]

    async def _sparse(texts: list[str]) -> list[dict[str, float]]:
        captured["sparse"] = list(texts)
        return [{"t": 1.0} for _ in texts]

    embeddings.embed_dense = AsyncMock(side_effect=_dense)
    embeddings.embed_sparse = AsyncMock(side_effect=_sparse)

    upserted: list[dict[str, Any]] = []
    vectorstore = AsyncMock()
    vectorstore.upsert = AsyncMock(side_effect=lambda rows: upserted.extend(rows))
    persistence = AsyncMock()
    persistence.add_audit_event = AsyncMock()

    svc = IngestService(
        docling=_OkDocling(),
        embeddings=embeddings,
        vectorstore=vectorstore,
        persistence=persistence,
    )
    result = await svc.ingest_text(text=huge)

    assert result["chunks"] >= 2
    assert all(len(t) <= MAX_EMBED_CHARS for t in captured["dense"])
    assert all(len(row["text"]) <= MAX_EMBED_CHARS for row in upserted)
    assert upserted[0]["metadata"]["embed_split"] is True
    assert upserted[0]["chunk_id"] == "d1"
    assert upserted[1]["chunk_id"] == "d1-p1"


@pytest.mark.asyncio
async def test_ingest_file_uses_shared_embed_guard(tmp_path) -> None:  # type: ignore[no-untyped-def]
    src = tmp_path / "reg.docx"
    src.write_bytes(b"fake")
    huge = ("пункт " * 2000).strip()
    assert len(huge) > MAX_EMBED_CHARS

    class _FileDocling:
        async def convert(self, *, source_path: str | None = None, text: str | None = None) -> dict:
            _ = (source_path, text)
            return {"chunks": [{"chunk_id": "f1", "text": huge}]}

    embeddings = AsyncMock()
    embeddings.embed_dense = AsyncMock(side_effect=lambda texts: [[0.1] for _ in texts])
    embeddings.embed_sparse = AsyncMock(side_effect=lambda texts: [{} for _ in texts])
    upserted: list[dict[str, Any]] = []
    vectorstore = AsyncMock()
    vectorstore.upsert = AsyncMock(side_effect=lambda rows: upserted.extend(rows))
    persistence = AsyncMock()
    persistence.add_audit_event = AsyncMock()

    svc = IngestService(
        docling=_FileDocling(),
        embeddings=embeddings,
        vectorstore=vectorstore,
        persistence=persistence,
    )
    result = await svc.ingest_file(source_path=src, document_title="Регламент")

    assert result["chunks"] >= 2
    assert result["document_title"] == "Регламент"
    assert all(len(row["text"]) <= MAX_EMBED_CHARS for row in upserted)
    dense_texts = embeddings.embed_dense.await_args.args[0]
    assert all(len(t) <= MAX_EMBED_CHARS for t in dense_texts)
