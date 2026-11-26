"""
ANCHOR: app.adapters.docling.HttpDoclingClient
PURPOSE: HTTP Docling convert client behind DOCLING_USE_STUB=false.
Dependencies: httpx
CRITICAL: Docling Serve ≥1.x uses POST /v1/convert/source with sources[].
DO:
- FileSourceRequest (kind=file, base64_string, filename) for local/docx/text
- HttpSourceRequest (kind=http, url) for remote URLs
DONT:
- POST legacy /convert or file_sources/http_sources fields (422 on 1.26)
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from app.adapters.docling.port import DoclingClient
from app.domain.errors import AppError, UpstreamTimeoutError


def _chunk_text(body: str, *, source_path: str | None = None) -> dict[str, Any]:
    paragraphs = [p.strip() for p in body.split("\n") if p.strip()] or ([body] if body else [])
    chunks = [
        {
            "chunk_id": f"docling-{uuid4().hex[:8]}",
            "text": p,
            "token_count": max(1, len(p.split())),
        }
        for p in paragraphs
    ]
    return {"source_path": source_path, "chunks": chunks, "text": body}


def _extract_text(data: dict[str, Any]) -> str:
    """Best-effort text extraction from Docling Serve v1 convert response."""
    if not isinstance(data, dict):
        return str(data)
    # Common shapes: document / documents[] with md_content | text_content | json_content
    docs: list[Any] = []
    if "document" in data and data["document"] is not None:
        docs.append(data["document"])
    if isinstance(data.get("documents"), list):
        docs.extend(data["documents"])
    texts: list[str] = []
    for doc in docs:
        if isinstance(doc, str):
            texts.append(doc)
            continue
        if not isinstance(doc, dict):
            continue
        for key in ("md_content", "text_content", "html_content"):
            val = doc.get(key)
            if isinstance(val, str) and val.strip():
                texts.append(val)
                break
        else:
            json_content = doc.get("json_content")
            if isinstance(json_content, dict):
                texts.append(str(json_content))
    if texts:
        return "\n\n".join(texts)
    for key in ("md_content", "text_content", "text", "markdown"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return ""


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

    def _headers(self, *, json_body: bool = False) -> dict[str, str]:
        headers: dict[str, str] = {}
        if json_body:
            headers["Content-Type"] = "application/json"
        if self._api_key:
            # Docling Serve accepts X-Api-Key; Bearer kept for compatible proxies.
            headers["X-Api-Key"] = self._api_key
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _build_sources(
        self, *, source_path: str | None, text: str | None
    ) -> list[dict[str, Any]]:
        if source_path:
            parsed = urlparse(source_path)
            if parsed.scheme in ("http", "https"):
                return [{"kind": "http", "url": source_path}]
            path = Path(source_path)
            if not path.is_file():
                raise AppError(f"Docling source not found: {source_path}", code="VALIDATION_ERROR")
            b64 = base64.b64encode(path.read_bytes()).decode("ascii")
            return [{"kind": "file", "base64_string": b64, "filename": path.name}]
        if text is not None:
            b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
            return [{"kind": "file", "base64_string": b64, "filename": "inline.txt"}]
        raise AppError("Docling convert requires source_path or text", code="VALIDATION_ERROR")

    async def ping(self) -> bool:
        headers = self._headers()
        try:
            async with httpx.AsyncClient(timeout=min(self._timeout, 15.0)) as client:
                # Prefer /health; fall back to base URL / OpenAPI.
                for path in ("/health", "/docs", "/", ""):
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
        sources = self._build_sources(source_path=source_path, text=text)
        payload: dict[str, Any] = {
            "sources": sources,
            "options": {
                "to_formats": ["md", "text"],
            },
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/v1/convert/source",
                    headers=self._headers(json_body=True),
                    json=payload,
                )
                if resp.status_code == 422:
                    raise AppError(
                        f"Docling validation error (422): {resp.text}",
                        code="UPSTREAM_VALIDATION",
                    )
                resp.raise_for_status()
                data = resp.json()
        except UpstreamTimeoutError:
            raise
        except AppError:
            raise
        except httpx.TimeoutException as exc:
            raise UpstreamTimeoutError("Docling request timed out") from exc
        except httpx.HTTPError as exc:
            raise AppError("Docling upstream error", code="UPSTREAM_ERROR") from exc

        body = _extract_text(data if isinstance(data, dict) else {})
        if not body and text:
            body = text
        result = _chunk_text(body, source_path=source_path)
        result["raw"] = data
        return result


_: DoclingClient = HttpDoclingClient(  # type: ignore[assignment]
    base_url="https://example.invalid/docling",
    api_key=None,
)
