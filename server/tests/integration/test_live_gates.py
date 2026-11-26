"""
ANCHOR: tests.integration.test_live_gates
PURPOSE: Live-gated smoke — skip unless RUN_LIVE_* set.
Dependencies: settings / real adapters
"""

from __future__ import annotations

import pytest

from tests.conftest import live_enabled

pytestmark = pytest.mark.integration


@pytest.mark.skipif(not live_enabled("RUN_LIVE_POSTGRES"), reason="RUN_LIVE_POSTGRES not set")
@pytest.mark.asyncio
async def test_live_postgres_ping() -> None:
    from app.config.factories import build_container
    from app.config.settings import Settings, clear_settings_cache

    clear_settings_cache()
    settings = Settings()
    container = build_container(settings)
    assert await container.persistence.ping() is True


@pytest.mark.skipif(not live_enabled("RUN_LIVE_LLM"), reason="RUN_LIVE_LLM not set")
@pytest.mark.asyncio
async def test_live_llm_complete() -> None:
    from app.config.factories import build_container
    from app.config.settings import Settings, clear_settings_cache

    clear_settings_cache()
    container = build_container(Settings())
    text = await container.llm.complete(system="Say OK", user="ping")
    assert isinstance(text, str) and text


@pytest.mark.skipif(not live_enabled("RUN_LIVE_QDRANT"), reason="RUN_LIVE_QDRANT not set")
@pytest.mark.asyncio
async def test_live_qdrant_ensure_and_roundtrip() -> None:
    from app.config.factories import build_container
    from app.config.settings import Settings, clear_settings_cache

    clear_settings_cache()
    container = build_container(Settings())
    vec = await container.embeddings.embed_dense(["smoke live qdrant"])
    assert vec and len(vec[0]) >= 8
    await container.vectorstore.upsert(
        [
            {
                "document_id": "live-smoke",
                "chunk_id": "live-smoke-chunk",
                "text": "smoke live qdrant",
                "dense_vector": vec[0],
                "source": "ingest",
            }
        ]
    )
    hits = await container.vectorstore.search(
        "smoke live qdrant", limit=3, dense_vector=vec[0]
    )
    assert isinstance(hits, list)


@pytest.mark.skipif(not live_enabled("RUN_LIVE_DOCLING"), reason="RUN_LIVE_DOCLING not set")
@pytest.mark.asyncio
async def test_live_docling_text_convert() -> None:
    from app.config.factories import build_container
    from app.config.settings import Settings, clear_settings_cache

    clear_settings_cache()
    container = build_container(Settings())
    out = await container.docling.convert(text="Краткий тестовый абзац для Docling Serve.")
    assert out.get("chunks")


@pytest.mark.e2e
@pytest.mark.skipif(not live_enabled("RUN_LIVE_E2E"), reason="RUN_LIVE_E2E not set")
@pytest.mark.asyncio
async def test_live_e2e_appeal_roundtrip() -> None:
    """Smoke: create appeal with first message against live stack; assert response shape."""
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
