"""
ANCHOR: tests.adapters.test_cli
PURPOSE: rag-server / python -m app.cli check + ingest entrypoints.
Dependencies: app.cli
"""

from __future__ import annotations

import pytest

from app.cli import main
from tests.conftest import require_all_core_services


@pytest.mark.integration
def test_cli_check_exits_zero() -> None:
    require_all_core_services()
    assert main(["check"]) == 0


@pytest.mark.parametrize("command", ["ingest-file", "ingest", "ingest-docx"])
def test_cli_ingest_accepts_universal_name_and_aliases(
    command: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Naming only: `ingest-file` plus aliases `ingest` / `ingest-docx` → _run_ingest."""
    calls: list[tuple[str, str | None]] = []

    async def _fake_ingest(path: str, *, document_title: str | None) -> int:
        calls.append((path, document_title))
        return 0

    monkeypatch.setattr("app.cli._run_ingest", _fake_ingest)
    assert main([command, "/tmp/sample.pdf", "--title", "Sample"]) == 0
    assert calls == [("/tmp/sample.pdf", "Sample")]
