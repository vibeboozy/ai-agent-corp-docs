"""
ANCHOR: app.adapters.stubs.escalation
PURPOSE: StubEscalationNotifier — deterministic fixture responses (skeleton).
Dependencies: app.adapters.escalation.port.EscalationNotifier
DO:
- Keep offline and side-effect free
DONT:
- Perform real network I/O
"""

from __future__ import annotations

from typing import Any

from app.adapters.escalation.port import EscalationNotifier


class StubEscalationNotifier:
    """Stub provider skeleton."""

    async def invoke(self, *args: Any, **kwargs: Any) -> Any:
        # TODO: return deterministic fixtures for demo/tests
        raise NotImplementedError("StubEscalationNotifier fixture responses not implemented")


_: EscalationNotifier = StubEscalationNotifier()  # type: ignore[assignment]
