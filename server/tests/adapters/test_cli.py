"""
ANCHOR: tests.adapters.test_cli
PURPOSE: rag-server / python -m app.cli check entrypoints under stubs.
Dependencies: app.cli
"""

from __future__ import annotations

import subprocess
import sys

from app.cli import main


def test_cli_check_stubs_exit_zero() -> None:
    assert main(["check"]) == 0


def test_module_cli_check_subprocess() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "app.cli", "check"],
        cwd=str(__file__).rsplit("/tests/", 1)[0],
        env={**dict(**{k: v for k, v in __import__("os").environ.items()}), "USE_STUBS": "true"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "overall: ok" in proc.stdout
