"""
ANCHOR: app.adapters.docling.HttpDoclingClient
PURPOSE: HTTP Docling convert client with OCR options + HybridChunker-style chunking.
Dependencies: httpx; Settings DOCLING_*; pdf_split for large local PDFs
CRITICAL: Docling Serve ≥1.x uses POST /v1/convert/source with sources[].
DO:
- FileSourceRequest (kind=file, base64_string, filename) for local/docx/text
- HttpSourceRequest (kind=http, url) for remote URLs
- Apply HybridChunker token window (max/overlap/min) after convert
- Split local PDFs above DOCLING_PDF_SPLIT_PAGES via options.page_range + merge
DONT:
- POST legacy /convert or file_sources/http_sources fields (422 on 1.26)
- Depend on docling-core for concatenate (page numbers shift)
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from app.adapters.docling.pdf_split import (
    PartCache,
    extract_json_content,
    merge_part_json_contents,
    merge_part_markdown,
    page_ranges,
    pdf_page_count,
    should_split_pdf,
)
from app.adapters.docling.port import DoclingClient
from app.domain.errors import AppError, UpstreamTimeoutError

logger = logging.getLogger(__name__)


def _approx_tokens(text: str) -> list[str]:
    """Whitespace tokenization stand-in for BAAI/bge-m3 (no heavy tokenizer dep)."""
    return [t for t in (text or "").split() if t]


# Prefer section / numbered-clause boundaries over blind token windows.
_SECTION_SPLIT_RE = re.compile(
    r"(?m)(?="
    r"^#{1,6}\s+"
    r"|^\*\*\d+(?:\.\d+)*\.?\*\*"
    r"|^\d+(?:\.\d+)*\.\s+"
    r"|<!--\s*page-break\s*-->"
    r")"
)
_SECTION_TITLE_RE = re.compile(
    r"(?m)^(?:#{1,6}\s+|\*\*)?(\d+(?:\.\d+)*\.?\s+[^\n*]{1,120}|\d+(?:\.\d+)*\.)"
)


def split_sections(body: str) -> list[tuple[str | None, str]]:
    """
    Split markdown/regulation text into (section_title, body) pairs.

    Keeps numbered clauses (7.2., **17.3.**) and headings intact so hybrid
    windows do not start mid-sentence mid-clause.
    """
    text = (body or "").strip()
    if not text:
        return []
    parts = _SECTION_SPLIT_RE.split(text)
    out: list[tuple[str | None, str]] = []
    for part in parts:
        part = part.strip()
        if not part or part.startswith("<!--"):
            continue
        title = None
        m = _SECTION_TITLE_RE.search(part[:160])
        if m:
            title = m.group(1).strip().rstrip("*").strip()
        out.append((title, part))
    return out or [(None, text)]


def _window_tokens(
    tokens: list[str],
    *,
    max_tokens: int,
    overlap_tokens: int,
    min_tokens: int,
    section_title: str | None,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    if not tokens:
        return chunks
    if len(tokens) <= max_tokens:
        text = " ".join(tokens)
        chunks.append(
            {
                "chunk_id": f"docling-{uuid4().hex[:8]}",
                "text": text,
                "token_count": len(tokens),
                "section_title": section_title,
                "locator": section_title,
            }
        )
        return chunks
    step = max(1, max_tokens - overlap_tokens)
    start = 0
    while start < len(tokens):
        window = tokens[start : start + max_tokens]
        # Prefer ending on a sentence-ish token when possible.
        if len(window) == max_tokens:
            for back in range(len(window) - 1, max(min_tokens, len(window) // 2), -1):
                if window[back].endswith((".", "!", "?", "…", "»")):
                    window = window[: back + 1]
                    break
        if len(window) < min_tokens and chunks:
            break
        text = " ".join(window)
        chunks.append(
            {
                "chunk_id": f"docling-{uuid4().hex[:8]}",
                "text": text,
                "token_count": len(window),
                "section_title": section_title,
                "locator": section_title,
            }
        )
        if start + len(window) >= len(tokens):
            break
        start += max(1, len(window) - overlap_tokens) if len(window) < max_tokens else step
    return chunks


def hybrid_chunk_text(
    body: str,
    *,
    source_path: str | None = None,
    chunker: str = "HybridChunker",
    tokenizer: str = "BAAI/bge-m3",
    max_tokens: int = 512,
    overlap_tokens: int = 64,
    min_tokens: int = 32,
) -> dict[str, Any]:
    """
    Section-aware HybridChunker-style windows from DOCLING_CHUNK_* env.

    Splits on regulation headings / numbered clauses first, then applies
    overlapping token windows inside each section (sentence-end bias).
    """
    max_tokens = max(1, int(max_tokens))
    overlap_tokens = max(0, min(int(overlap_tokens), max_tokens - 1))
    min_tokens = max(1, int(min_tokens))
    chunks: list[dict[str, Any]] = []
    for section_title, section_body in split_sections(body):
        tokens = _approx_tokens(section_body)
        if not tokens:
            continue
        # Tiny orphan fragments attach to previous chunk when possible.
        if len(tokens) < min_tokens and chunks and section_title is None:
            prev = chunks[-1]
            merged = f"{prev['text']} {' '.join(tokens)}".strip()
            prev["text"] = merged
            prev["token_count"] = len(_approx_tokens(merged))
            continue
        chunks.extend(
            _window_tokens(
                tokens,
                max_tokens=max_tokens,
                overlap_tokens=overlap_tokens,
                min_tokens=min_tokens,
                section_title=section_title,
            )
        )

    return {
        "source_path": source_path,
        "chunks": chunks,
        "text": body,
        "chunker": chunker,
        "tokenizer": tokenizer,
    }


def _extract_text(data: dict[str, Any]) -> str:
    """Best-effort text extraction from Docling Serve v1 convert response."""
    if not isinstance(data, dict):
        return str(data)
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
        connect_timeout_s: float = 30.0,
        concurrency: int = 2,
        split_pages: bool = True,
        pdf_split_pages: int = 40,
        pdf_part_cache_dir: str | None = None,
        ocr_langs: str = "ru,en",
        chunker: str = "HybridChunker",
        chunk_tokenizer: str = "BAAI/bge-m3",
        chunk_max_tokens: int = 512,
        chunk_overlap_tokens: int = 64,
        chunk_min_tokens: int = 32,
        allow_hosts: set[str] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_s
        self._connect_timeout = connect_timeout_s
        self._semaphore = asyncio.Semaphore(max(1, int(concurrency)))
        self._split_pages = split_pages
        # Max pages per Docling request for local PDFs; 0 disables range splitting.
        self._pdf_split_pages = max(0, int(pdf_split_pages))
        cache_dir = (pdf_part_cache_dir or "").strip()
        self._part_cache = PartCache(Path(cache_dir)) if cache_dir else None
        self._ocr_langs = [p.strip() for p in (ocr_langs or "").split(",") if p.strip()]
        self._chunker = chunker
        self._chunk_tokenizer = chunk_tokenizer
        self._chunk_max_tokens = chunk_max_tokens
        self._chunk_overlap_tokens = chunk_overlap_tokens
        self._chunk_min_tokens = chunk_min_tokens
        self._allow_hosts = allow_hosts or set()
        if self._allow_hosts:
            host = (urlparse(self._base_url).hostname or "").lower()
            if host and host not in self._allow_hosts:
                raise AppError(f"Docling host not allowlisted: {host}", code="EGRESS_DENIED")

    def _httpx_timeout(self) -> httpx.Timeout:
        return httpx.Timeout(self._timeout, connect=self._connect_timeout)

    def _headers(self, *, json_body: bool = False) -> dict[str, str]:
        headers: dict[str, str] = {}
        if json_body:
            headers["Content-Type"] = "application/json"
        if self._api_key:
            headers["X-Api-Key"] = self._api_key
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _page_break_placeholder(self) -> str:
        return "\n\n<!-- page-break -->\n\n"

    def _convert_options(
        self, *, page_range: tuple[int, int] | None = None, include_json: bool = False
    ) -> dict[str, Any]:
        formats = ["md", "text"]
        if include_json:
            formats.append("json")
        options: dict[str, Any] = {
            "to_formats": formats,
            "do_ocr": bool(self._ocr_langs),
        }
        if self._ocr_langs:
            options["ocr_lang"] = list(self._ocr_langs)
        if self._split_pages:
            # Page-break placeholder helps HybridChunker keep section boundaries.
            options["md_page_break_placeholder"] = self._page_break_placeholder()
        if page_range is not None:
            start, end = page_range
            options["page_range"] = [int(start), int(end)]
        return options

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

    def _local_pdf_path(self, source_path: str | None) -> Path | None:
        if not source_path:
            return None
        parsed = urlparse(source_path)
        if parsed.scheme in ("http", "https"):
            return None
        path = Path(source_path)
        if path.is_file() and path.suffix.lower() == ".pdf":
            return path
        return None

    async def ping(self) -> bool:
        headers = self._headers()
        try:
            async with httpx.AsyncClient(timeout=self._httpx_timeout()) as client:
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

    async def _post_convert(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with self._semaphore:
            try:
                async with httpx.AsyncClient(timeout=self._httpx_timeout()) as client:
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
        return data if isinstance(data, dict) else {"raw": data}

    def _finalize(
        self,
        *,
        body: str,
        source_path: str | None,
        raw: Any,
        options: dict[str, Any],
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = hybrid_chunk_text(
            body,
            source_path=source_path,
            chunker=self._chunker,
            tokenizer=self._chunk_tokenizer,
            max_tokens=self._chunk_max_tokens,
            overlap_tokens=self._chunk_overlap_tokens,
            min_tokens=self._chunk_min_tokens,
        )
        result["raw"] = raw
        result["options"] = options
        if extra:
            result.update(extra)
        return result

    async def _convert_pdf_parts(self, path: Path) -> dict[str, Any]:
        n_pages = pdf_page_count(path)
        threshold = self._pdf_split_pages
        ranges = page_ranges(n_pages, threshold)
        logger.info(
            "Docling PDF split: path=%s pages=%s threshold=%s parts=%s",
            path.name,
            n_pages,
            threshold,
            len(ranges),
        )
        sources = self._build_sources(source_path=str(path), text=None)
        digest = PartCache.file_digest(path) if self._part_cache else ""
        page_break = self._page_break_placeholder()

        async def _one(start: int, end: int) -> tuple[int, int, str, Any, dict[str, Any]]:
            cached = (
                self._part_cache.load(digest=digest, start=start, end=end)
                if self._part_cache
                else None
            )
            if cached is not None:
                data = cached.get("raw") if isinstance(cached.get("raw"), dict) else cached
                body = str(cached.get("text") or "")
                if not body and isinstance(data, dict):
                    body = _extract_text(data)
                return start, end, body, data if isinstance(data, dict) else {}, cached

            options = self._convert_options(page_range=(start, end), include_json=True)
            payload = {"sources": sources, "options": options}
            data = await self._post_convert(payload)
            body = _extract_text(data)
            if self._part_cache:
                self._part_cache.store(
                    digest=digest,
                    start=start,
                    end=end,
                    payload={"text": body, "raw": data, "page_range": [start, end]},
                )
            return start, end, body, data, options

        # Parallelism capped by DOCLING_CONCURRENCY via the shared semaphore.
        part_results = await asyncio.gather(*[_one(s, e) for s, e in ranges])
        md_parts = [(s, e, text) for s, e, text, _data, _opts in part_results]
        body = merge_part_markdown(md_parts, page_break=page_break)
        json_parts = [
            (s, e, extract_json_content(data if isinstance(data, dict) else None))
            for s, e, _text, data, _opts in part_results
        ]
        merged_json = merge_part_json_contents(json_parts)
        options = self._convert_options(include_json=True)
        options["page_ranges"] = [[s, e] for s, e in ranges]
        raw = {
            "document": {
                "md_content": body,
                "text_content": body,
                "json_parts": merged_json,
            },
            "pdf_split": {
                "n_pages": n_pages,
                "threshold": threshold,
                "page_ranges": [[s, e] for s, e in ranges],
                "parts": len(ranges),
                "cache": bool(self._part_cache),
            },
        }
        return self._finalize(
            body=body,
            source_path=str(path),
            raw=raw,
            options=options,
            extra={"pdf_split": raw["pdf_split"]},
        )

    async def convert(self, *, source_path: str | None = None, text: str | None = None) -> dict[str, Any]:
        local_pdf = self._local_pdf_path(source_path)
        if local_pdf is not None and self._pdf_split_pages > 0:
            try:
                n_pages = pdf_page_count(local_pdf)
            except Exception as exc:
                raise AppError(
                    f"Failed to read PDF page count: {local_pdf}",
                    code="VALIDATION_ERROR",
                ) from exc
            if should_split_pdf(n_pages=n_pages, threshold=self._pdf_split_pages):
                return await self._convert_pdf_parts(local_pdf)

        sources = self._build_sources(source_path=source_path, text=text)
        options = self._convert_options()
        payload: dict[str, Any] = {
            "sources": sources,
            "options": options,
        }
        data = await self._post_convert(payload)
        body = _extract_text(data)
        if not body and text:
            body = text
        return self._finalize(
            body=body,
            source_path=source_path,
            raw=data,
            options=options,
        )


_: DoclingClient = HttpDoclingClient(  # type: ignore[assignment]
    base_url="https://example.invalid/docling",
    api_key=None,
)
