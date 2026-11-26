"""
ANCHOR: tests.adapters.test_cli
PURPOSE: rag-server / python -m app.cli check entrypoints (when deps reachable).
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
