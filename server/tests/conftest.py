"""
ANCHOR: tests.conftest
PURPOSE: Shared pytest fixtures (ASGI client placeholder).
Dependencies: app.main, httpx
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())
