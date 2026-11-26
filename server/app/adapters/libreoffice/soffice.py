"""
ANCHOR: app.adapters.libreoffice.soffice
PURPOSE: Real soffice converter behind LIBREOFFICE_USE_STUB=false.
Dependencies: asyncio subprocess
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.adapters.libreoffice.port import LibreOfficeConverter
from app.domain.errors import AppError, UpstreamTimeoutError


class SofficeLibreOffice:
    def __init__(self, *, soffice_path: str = "soffice", timeout_s: float = 120.0) -> None:
        self._soffice = soffice_path
        self._timeout = timeout_s

    async def convert_to_pdf(self, source_path: str, dest_dir: str) -> str:
        Path(dest_dir).mkdir(parents=True, exist_ok=True)
        cmd = [
            self._soffice,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            dest_dir,
            source_path,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
            except TimeoutError as exc:
                proc.kill()
                raise UpstreamTimeoutError("LibreOffice conversion timed out") from exc
            if proc.returncode != 0:
                raise AppError("LibreOffice conversion failed", code="UPSTREAM_ERROR")
        except FileNotFoundError as exc:
            raise AppError("soffice binary not found", code="DEPENDENCY_MISSING") from exc
        return str(Path(dest_dir) / Path(source_path).with_suffix(".pdf").name)


_: LibreOfficeConverter = SofficeLibreOffice()  # type: ignore[assignment]
