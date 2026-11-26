"""
ANCHOR: tests.adapters.test_cli
PURPOSE: rag-server / python -m app.cli check entrypoints (live-gated).
Dependencies: app.cli
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from app.cli import main
from tests.conftest import live_enabled


@pytest.mark.integration
@pytest.mark.skipif(
    not live_enabled("RUN_LIVE_TESTS"),
    reason="RUN_LIVE_TESTS not set (CLI check needs live deps)",
)
def test_cli_check_exits_zero_when_live() -> None:
    assert main(["check"]) == 0


@pytest.mark.integration
@pytest.mark.skipif(
    not live_enabled("RUN_LIVE_TESTS"),
    reason="RUN_LIVE_TESTS not set (CLI check needs live deps)",
)
def test_module_cli_check_subprocess() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "app.cli", "check"],
        cwd=str(__file__).rsplit("/tests/", 1)[0],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "overall: ok" in proc.stdout
    assert "[OK] llm" in proc.stdout
    assert "mode=" not in proc.stdout
