"""
ANCHOR: tests.adapters.test_connectivity
PURPOSE: Connectivity report shape (mocked) + live probes when services up.
Dependencies: connectivity service, adapters
"""

from __future__ import annotations

import pytest

from app.application.connectivity.service import ConnectivityService
from app.config.factories import build_container
from app.config.settings import Settings, clear_settings_cache
from tests.conftest import require_services


@pytest.mark.asyncio
async def test_connectivity_report_shape_with_mocks() -> None:
    async def _ok() -> bool:
        return True

    class _Pinger:
        ping = staticmethod(_ok)

    svc = ConnectivityService(
        llm=_Pinger(),
        embeddings=_Pinger(),
        vectorstore=_Pinger(),
        docling=_Pinger(),
        persistence=_Pinger(),
    )
    report = await svc.check_report()
    assert report["status"] == "ok"
    names = {d["name"] for d in report["dependencies"]}
    assert names == {"llm", "embeddings", "qdrant", "docling", "postgres"}
    for dep in report["dependencies"]:
        assert dep["ok"] is True
        assert "mode" not in dep


@pytest.mark.asyncio
async def test_connectivity_degraded_on_ping_failure() -> None:
    async def _fail() -> bool:
        raise RuntimeError("down")

    class _Ok:
        async def ping(self) -> bool:
            return True

    class _Bad:
        ping = staticmethod(_fail)

    svc = ConnectivityService(
        llm=_Ok(),
        embeddings=_Ok(),
        vectorstore=_Bad(),
        docling=_Ok(),
        persistence=_Ok(),
    )
    report = await svc.check_report()
    assert report["status"] == "degraded"
    qdrant = next(d for d in report["dependencies"] if d["name"] == "qdrant")
    assert qdrant["ok"] is False
    assert "mode" not in qdrant


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_llm_ping() -> None:
    require_services("llm")
    clear_settings_cache()
    c = build_container(Settings())
    assert await c.llm.ping() is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_embeddings_ping() -> None:
    require_services("embeddings")
    clear_settings_cache()
    c = build_container(Settings())
    assert await c.embeddings.ping() is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_qdrant_ping() -> None:
    require_services("qdrant")
    clear_settings_cache()
    c = build_container(Settings())
    assert await c.vectorstore.ping() is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_docling_ping() -> None:
    require_services("docling")
    clear_settings_cache()
    c = build_container(Settings())
    assert await c.docling.ping() is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_postgres_ping_via_connectivity() -> None:
    require_services("postgres")
    clear_settings_cache()
    c = build_container(Settings())
    assert await c.persistence.ping() is True
    report = await c.connectivity.check_report()
    pg = next(d for d in report["dependencies"] if d["name"] == "postgres")
    assert pg["ok"] is True
    assert "mode" not in pg
