"""
ANCHOR: app.adapters.stubs.libreoffice
PURPOSE: StubLibreOffice — deterministic fixture responses (skeleton).
Dependencies: app.adapters.libreoffice.port.LibreOfficeConverter
DO:
- Keep offline and side-effect free
DONT:
- Perform real network I/O
"""

from __future__ import annotations

from typing import Any

from app.adapters.libreoffice.port import LibreOfficeConverter


class StubLibreOffice:
    """Stub provider skeleton."""

    async def invoke(self, *args: Any, **kwargs: Any) -> Any:
        # TODO: return deterministic fixtures for demo/tests
        raise NotImplementedError("StubLibreOffice fixture responses not implemented")


_: LibreOfficeConverter = StubLibreOffice()  # type: ignore[assignment]
