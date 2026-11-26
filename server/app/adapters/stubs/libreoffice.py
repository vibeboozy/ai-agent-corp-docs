"""
ANCHOR: app.adapters.stubs.libreoffice
PURPOSE: StubLibreOffice — no-op path echo for convert_to_pdf.
Dependencies: app.adapters.libreoffice.port.LibreOfficeConverter
DO:
- Keep offline and side-effect free
DONT:
- Invoke real soffice
"""

from __future__ import annotations

from pathlib import Path

from app.adapters.libreoffice.port import LibreOfficeConverter


class StubLibreOffice:
    """Returns a fake PDF path without running soffice."""

    async def convert_to_pdf(self, source_path: str, dest_dir: str) -> str:
        name = Path(source_path).with_suffix(".pdf").name
        return str(Path(dest_dir) / name)


_: LibreOfficeConverter = StubLibreOffice()  # type: ignore[assignment]
