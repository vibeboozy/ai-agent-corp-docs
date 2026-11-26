"""
ANCHOR: tests.conftest
PURPOSE: Shared pytest fixtures (ASGI client + DI cache resets).
Dependencies: app.main, app.config.factories
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.config.factories import reset_container
from app.config.settings import clear_settings_cache
from app.main import create_app


@pytest.fixture(autouse=True)
def _reset_di() -> None:
    clear_settings_cache()
    reset_container()
    yield
    clear_settings_cache()
    reset_container()


@pytest.fixture
def client() -> TestClient:
    with TestClient(create_app()) as c:
        yield c


def live_enabled(*flags: str) -> bool:
    """True only when every named RUN_LIVE_* env is truthy."""
    truthy = {"1", "true", "yes", "on"}
    return all(os.getenv(f, "0").lower() in truthy for f in flags)
