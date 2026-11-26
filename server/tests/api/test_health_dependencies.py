"""
ANCHOR: tests.api.test_health_dependencies
PURPOSE: HTTP dependency connectivity report shape; live OK gated by RUN_LIVE_*.
Dependencies: app.main
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import live_enabled


def test_health_dependencies_endpoint_shape(client: TestClient) -> None:
    """Endpoint returns structure even when upstreams are unreachable (degraded)."""
    for path in ("/health/dependencies", "/api/v1/health/dependencies"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        body = resp.json()
        assert body["status"] in {"ok", "degraded"}
        assert len(body["dependencies"]) == 5
        names = {d["name"] for d in body["dependencies"]}
        assert names == {"llm", "embeddings", "qdrant", "docling", "postgres"}
        assert all("mode" not in d for d in body["dependencies"])


@pytest.mark.integration
@pytest.mark.skipif(
    not live_enabled("RUN_LIVE_TESTS"),
    reason="RUN_LIVE_TESTS not set",
)
def test_health_dependencies_all_ok_when_live(client: TestClient) -> None:
    resp = client.get("/health/dependencies")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert all(d["ok"] for d in body["dependencies"])
