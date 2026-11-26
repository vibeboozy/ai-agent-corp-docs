"""
ANCHOR: tests.api.test_health_dependencies
PURPOSE: HTTP dependency connectivity report shape; live OK when services up.
Dependencies: app.main
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import require_all_core_services


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
def test_health_dependencies_all_ok(client: TestClient) -> None:
    require_all_core_services()
    resp = client.get("/health/dependencies")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert all(d["ok"] for d in body["dependencies"])
