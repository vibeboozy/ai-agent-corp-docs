"""
ANCHOR: tests.api.test_health
PURPOSE: Smoke test: health endpoint and OpenAPI path presence.
Dependencies: app.main
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_openapi_lists_v1_paths(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    for path in (
        "/api/v1/appeals",
        "/api/v1/appeals/{appeal_id}",
        "/api/v1/appeals/{appeal_id}/messages",
        "/api/v1/appeals/{appeal_id}/officer-reply",
        "/api/v1/stats",
        "/api/v1/health/dependencies",
        "/health/dependencies",
    ):
        assert path in paths
