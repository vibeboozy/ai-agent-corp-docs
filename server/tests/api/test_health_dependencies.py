"""
ANCHOR: tests.api.test_health_dependencies
PURPOSE: HTTP + CLI connectivity check under stubs.
Dependencies: app.main, app.cli
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.cli import main


def test_health_dependencies_endpoint(client: TestClient) -> None:
    for path in ("/health/dependencies", "/api/v1/health/dependencies"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        body = resp.json()
        assert body["status"] == "ok"
        assert len(body["dependencies"]) == 5
        assert all(d["ok"] for d in body["dependencies"])


def test_cli_check_exits_zero_under_stubs(capsys) -> None:
    code = main(["check"])
    captured = capsys.readouterr()
    assert code == 0
    assert "overall: ok" in captured.out
    assert "[OK] llm" in captured.out
    assert "[OK] postgres" in captured.out
