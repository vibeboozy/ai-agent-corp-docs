"""
ANCHOR: tests.application.test_ingest_glossary_text
PURPOSE: Ingest expands abbreviations into chunk TEXT before dense/sparse embed.
Dependencies: IngestService + Fake ports / glossary
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.application.ingest.service import IngestService
from app.domain.glossary import AbbreviationGlossary


class _Docling:
    async def convert(self, *, source_path: str | None = None, text: str | None = None) -> dict:
        _ = source_path
        body = text or ""
        return {"chunks": [{"chunk_id": "c1", "text": body}]}


@pytest.mark.asyncio
async def test_ingest_enriches_chunk_text_before_embed() -> None:
    captured: dict[str, Any] = {}

    embeddings = AsyncMock()

    async def _dense(texts: list[str]) -> list[list[float]]:
        captured["dense_texts"] = list(texts)
        return [[0.1, 0.2] for _ in texts]

    async def _sparse(texts: list[str]) -> list[dict[str, float]]:
        captured["sparse_texts"] = list(texts)
        return [{"x": 1.0} for _ in texts]

    embeddings.embed_dense = AsyncMock(side_effect=_dense)
    embeddings.embed_sparse = AsyncMock(side_effect=_sparse)

    upserted: list[dict[str, Any]] = []

    async def _upsert(chunks: list[dict[str, Any]]) -> None:
        upserted.extend(chunks)

    vectorstore = AsyncMock()
    vectorstore.upsert = AsyncMock(side_effect=_upsert)
    persistence = AsyncMock()
    persistence.add_audit_event = AsyncMock()

    svc = IngestService(
        docling=_Docling(),
        embeddings=embeddings,
        vectorstore=vectorstore,
        persistence=persistence,
        glossary=AbbreviationGlossary.from_defaults(),
    )
    await svc.ingest_text(text="На проекте работает РП.")

    assert captured["dense_texts"]
    assert "РП (Руководитель проекта)" in captured["dense_texts"][0]
    assert "РП (Руководитель проекта)" in captured["sparse_texts"][0]
    assert "РП (Руководитель проекта)" in upserted[0]["text"]
    assert upserted[0]["metadata"]["abbreviations"]["РП"] == "Руководитель проекта"
