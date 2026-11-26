"""
ANCHOR: tests.conftest
PURPOSE: Shared pytest fixtures (ASGI client + stub resets).
Dependencies: app.main, app.config.factories, stubs.fixtures
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

# Force stubs for unit/API tests unless a live suite opts in.
os.environ.setdefault("USE_STUBS", "true")
os.environ.setdefault("PERSISTENCE_USE_STUB", "true")

from app.adapters.stubs.fixtures import SHARED_FIXTURE_KB
from app.config.factories import reset_container
from app.config.settings import clear_settings_cache
from app.main import create_app


@pytest.fixture(autouse=True)
def _reset_stubs() -> None:
    SHARED_FIXTURE_KB.reset()
    clear_settings_cache()
    reset_container()
    yield
    SHARED_FIXTURE_KB.reset()
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
