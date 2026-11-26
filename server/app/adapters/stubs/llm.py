"""
ANCHOR: app.adapters.stubs.llm
PURPOSE: StubLLMClient — deterministic fixture responses (skeleton).
Dependencies: app.adapters.llm.port.LLMClient
DO:
- Keep offline and side-effect free
DONT:
- Perform real network I/O
"""

from __future__ import annotations

from typing import Any

from app.adapters.llm.port import LLMClient


class StubLLMClient:
    """Stub provider skeleton."""

    async def invoke(self, *args: Any, **kwargs: Any) -> Any:
        # TODO: return deterministic fixtures for demo/tests
        raise NotImplementedError("StubLLMClient fixture responses not implemented")


_: LLMClient = StubLLMClient()  # type: ignore[assignment]
