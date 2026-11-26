"""
ANCHOR: app.adapters.libreoffice.port
PURPOSE: LibreOfficeConverter Protocol/ABC for soffice conversion.
Dependencies: typing.Protocol
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LibreOfficeConverter(Protocol):
    async def convert_to_pdf(self, source_path: str, dest_dir: str) -> str:
        """Convert office document to PDF; return output path."""
        ...
