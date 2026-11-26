"""
ANCHOR: tests.adapters.test_cli
PURPOSE: rag-server / python -m app.cli check entrypoints (gated by RUN_LIVE_TESTS).
Dependencies: app.cli
"""

from __future__ import annotations

import pytest

from app.cli import main
from tests.conftest import env_flag


@pytest.mark.integration
@pytest.mark.skipif(
    not env_flag("RUN_LIVE_TESTS"),
    reason="RUN_LIVE_TESTS not set (CLI check needs live deps)",
)
def test_cli_check_exits_zero() -> None:
    assert main(["check"]) == 0
