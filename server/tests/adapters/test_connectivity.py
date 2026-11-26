"""
ANCHOR: tests.adapters.test_connectivity
PURPOSE: Stub connectivity always healthy; live probes gated by RUN_LIVE_*.
Dependencies: connectivity service, adapters
"""

from __future__ import annotations

import os

import pytest

from app.config.factories import build_container
from app.config.settings import Settings, clear_settings_cache
from tests.conftest import live_enabled


@pytest.mark.asyncio
async def test_stub_dependencies_all_healthy() -> None:
    clear_settings_cache()
    container = build_container(Settings(USE_STUBS=True))
    report = await container.connectivity.check_report()
    assert report["status"] == "ok"
    names = {d["name"] for d in report["dependencies"]}
    assert names == {"llm", "embeddings", "qdrant", "docling", "postgres"}
    for dep in report["dependencies"]:
        assert dep["ok"] is True
        assert dep["mode"] == "stub"


@pytest.mark.asyncio
async def test_stub_individual_pings() -> None:
    clear_settings_cache()
    c = build_container(Settings(USE_STUBS=True))
    assert await c.llm.ping() is True
    assert await c.embeddings.ping() is True
    assert await c.vectorstore.ping() is True
    assert await c.docling.ping() is True
    assert await c.persistence.ping() is True


@pytest.mark.integration
@pytest.mark.skipif(not live_enabled("RUN_LIVE_LLM"), reason="RUN_LIVE_LLM not set")
@pytest.mark.asyncio
async def test_live_llm_ping() -> None:
    os.environ["USE_STUBS"] = "false"
    os.environ["LLM_USE_STUB"] = "false"
    clear_settings_cache()
    c = build_container(Settings())
    assert await c.llm.ping() is True


@pytest.mark.integration
@pytest.mark.skipif(not live_enabled("RUN_LIVE_EMBEDDINGS"), reason="RUN_LIVE_EMBEDDINGS not set")
@pytest.mark.asyncio
async def test_live_embeddings_ping() -> None:
    os.environ["USE_STUBS"] = "false"
    os.environ["EMBEDDINGS_USE_STUB"] = "false"
    clear_settings_cache()
    c = build_container(Settings())
    assert await c.embeddings.ping() is True


@pytest.mark.integration
@pytest.mark.skipif(not live_enabled("RUN_LIVE_QDRANT"), reason="RUN_LIVE_QDRANT not set")
@pytest.mark.asyncio
async def test_live_qdrant_ping() -> None:
    os.environ["USE_STUBS"] = "false"
    os.environ["QDRANT_USE_STUB"] = "false"
    clear_settings_cache()
    c = build_container(Settings())
    assert await c.vectorstore.ping() is True


@pytest.mark.integration
@pytest.mark.skipif(not live_enabled("RUN_LIVE_DOCLING"), reason="RUN_LIVE_DOCLING not set")
@pytest.mark.asyncio
async def test_live_docling_ping() -> None:
    os.environ["USE_STUBS"] = "false"
    os.environ["DOCLING_USE_STUB"] = "false"
    clear_settings_cache()
    c = build_container(Settings())
    assert await c.docling.ping() is True


@pytest.mark.integration
@pytest.mark.skipif(not live_enabled("RUN_LIVE_POSTGRES"), reason="RUN_LIVE_POSTGRES not set")
@pytest.mark.asyncio
async def test_live_postgres_ping_via_connectivity() -> None:
    os.environ["USE_STUBS"] = "false"
    os.environ["PERSISTENCE_USE_STUB"] = "false"
    clear_settings_cache()
    c = build_container(Settings())
    assert await c.persistence.ping() is True
    report = await c.connectivity.check_report()
    pg = next(d for d in report["dependencies"] if d["name"] == "postgres")
    assert pg["ok"] is True
    assert pg["mode"] == "live"
