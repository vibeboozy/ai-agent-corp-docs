"""
ANCHOR: app.adapters.docling.HttpDoclingClient
PURPOSE: HTTP Docling convert client behind DOCLING_USE_STUB=false.
Dependencies: httpx
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from app.adapters.docling.port import DoclingClient
from app.domain.errors import AppError, UpstreamTimeoutError


class HttpDoclingClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        timeout_s: float = 300.0,
        allow_hosts: set[str] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_s
        self._allow_hosts = allow_hosts or set()
        if self._allow_hosts:
            host = (urlparse(self._base_url).hostname or "").lower()
            if host and host not in self._allow_hosts:
                raise AppError(f"Docling host not allowlisted: {host}", code="EGRESS_DENIED")

    async def ping(self) -> bool:
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            async with httpx.AsyncClient(timeout=min(self._timeout, 15.0)) as client:
                # Prefer /health; fall back to base URL reachability.
                for path in ("/health", "/", ""):
                    url = f"{self._base_url}{path}" if path else self._base_url
                    resp = await client.get(url, headers=headers)
                    if resp.status_code < 500:
                        return True
                return False
        except httpx.TimeoutException as exc:
            raise UpstreamTimeoutError("Docling ping timed out") from exc
        except httpx.HTTPError as exc:
            raise AppError("Docling ping failed", code="UPSTREAM_ERROR") from exc

    async def convert(self, *, source_path: str | None = None, text: str | None = None) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        payload = {"source_path": source_path, "text": text}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(f"{self._base_url}/convert", headers=headers, json=payload)
                resp.raise_for_status()
                return resp.json()
        except httpx.TimeoutException as exc:
            raise UpstreamTimeoutError("Docling request timed out") from exc
        except httpx.HTTPError as exc:
            raise AppError("Docling upstream error", code="UPSTREAM_ERROR") from exc


_: DoclingClient = HttpDoclingClient(  # type: ignore[assignment]
    base_url="https://example.invalid/docling",
    api_key=None,
)
