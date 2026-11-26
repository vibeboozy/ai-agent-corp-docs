"""
ANCHOR: tests.api.test_api_prefix
PURPOSE: API_PREFIX from Settings mounts appeals under the configured prefix.
Dependencies: create_app; Settings
"""

from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.config.settings import clear_settings_cache
from app.main import create_app


def test_custom_api_prefix_mounts_appeals(monkeypatch) -> None:
    monkeypatch.setenv("API_PREFIX", "/api/v2")
    clear_settings_cache()
    with TestClient(create_app()) as client:
        openapi = client.get("/openapi.json").json()["paths"]
        assert "/api/v2/appeals" in openapi
        assert "/api/v1/appeals" not in openapi
    # restore defaults for other tests
    os.environ.pop("API_PREFIX", None)
    clear_settings_cache()
