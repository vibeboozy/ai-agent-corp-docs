"""
ANCHOR: tests.integration.test_live_gates
PURPOSE: Live-gated smoke placeholders — skip unless RUN_LIVE_* set.
Dependencies: settings / optional real adapters
"""

from __future__ import annotations

import os

import pytest

from tests.conftest import live_enabled

pytestmark = pytest.mark.integration


@pytest.mark.skipif(not live_enabled("RUN_LIVE_POSTGRES"), reason="RUN_LIVE_POSTGRES not set")
@pytest.mark.asyncio
async def test_live_postgres_ping() -> None:
    os.environ["USE_STUBS"] = "false"
    os.environ["PERSISTENCE_USE_STUB"] = "false"
    from app.config.factories import build_container
    from app.config.settings import Settings, clear_settings_cache

    clear_settings_cache()
    settings = Settings()
    container = build_container(settings)
    assert await container.persistence.ping() is True


@pytest.mark.skipif(not live_enabled("RUN_LIVE_LLM"), reason="RUN_LIVE_LLM not set")
@pytest.mark.asyncio
async def test_live_llm_complete() -> None:
    os.environ["USE_STUBS"] = "false"
    os.environ["LLM_USE_STUB"] = "false"
    from app.config.factories import build_container
    from app.config.settings import Settings, clear_settings_cache

    clear_settings_cache()
    container = build_container(Settings())
    text = await container.llm.complete(system="Say OK", user="ping")
    assert isinstance(text, str) and text


@pytest.mark.skipif(not live_enabled("RUN_LIVE_E2E"), reason="RUN_LIVE_E2E not set")
@pytest.mark.asyncio
async def test_live_e2e_placeholder() -> None:
    pytest.skip("Live e2e scenario requires full infra; document path in DEMO.md")
