"""
ANCHOR: tests.integration.test_live_gates
PURPOSE: Live smoke — run when services reachable via Settings; else skip.
Dependencies: settings / real adapters
"""

from __future__ import annotations

import pytest

from tests.conftest import require_services

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_live_postgres_ping() -> None:
    require_services("postgres")
    from app.config.factories import build_container
    from app.config.settings import Settings, clear_settings_cache

    clear_settings_cache()
    settings = Settings()
    container = build_container(settings)
    assert await container.persistence.ping() is True


@pytest.mark.asyncio
async def test_live_llm_complete() -> None:
    require_services("llm")
    from app.config.factories import build_container
    from app.config.settings import Settings, clear_settings_cache

    clear_settings_cache()
    container = build_container(Settings())
    text = await container.llm.complete(system="Say OK", user="ping")
    assert isinstance(text, str) and text


@pytest.mark.asyncio
async def test_live_qdrant_ensure_and_roundtrip() -> None:
    require_services("qdrant", "embeddings")
    from app.config.factories import build_container
    from app.config.settings import Settings, clear_settings_cache

    clear_settings_cache()
    container = build_container(Settings())
    vec = await container.embeddings.embed_dense(["smoke live qdrant"])
    sparse = await container.embeddings.embed_sparse(["smoke live qdrant"])
    assert vec and len(vec[0]) >= 8
    await container.vectorstore.upsert(
        [
            {
                "document_id": "live-smoke",
                "chunk_id": "live-smoke-chunk",
                "text": "smoke live qdrant",
                "dense_vector": vec[0],
                "sparse_vector": sparse[0] if sparse else None,
                "source": "ingest",
            }
        ]
    )
    hits = await container.vectorstore.search(
        "smoke live qdrant",
        limit=3,
        dense_vector=vec[0],
        sparse_vector=sparse[0] if sparse else None,
    )
    assert isinstance(hits, list)


@pytest.mark.asyncio
async def test_live_docling_text_convert() -> None:
    require_services("docling")
    from app.config.factories import build_container
    from app.config.settings import Settings, clear_settings_cache

    clear_settings_cache()
    container = build_container(Settings())
    out = await container.docling.convert(text="Краткий тестовый абзац для Docling Serve.")
    assert out.get("chunks")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_live_e2e_appeal_roundtrip() -> None:
    """Smoke: create appeal with first message against live stack; assert response shape."""
    require_services("llm", "embeddings", "qdrant", "postgres")
    from app.config.factories import build_container
    from app.config.settings import Settings, clear_settings_cache

    clear_settings_cache()
    container = build_container(Settings())
    created = await container.appeals.create(
        first_message="Кто подписывает договоры на закупку?"
    )
    assert created.appeal.id is not None
    assert created.messages
    assert created.appeal.status.value in {
        "answered",
        "clarifying",
        "escalated",
        "open",
    }
