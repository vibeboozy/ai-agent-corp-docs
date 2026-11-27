"""
ANCHOR: app.adapters.docling.pdf_split
PURPOSE: Large-PDF page-range helpers for Docling Serve (count, ranges, merge, part cache).
Dependencies: pypdf (page count only); stdlib for cache/merge
DO:
- Split when n_pages > threshold into inclusive 1-based ranges
- Merge part markdown/json preserving absolute source page numbers
- Optional on-disk part cache under a configured directory
DONT:
- Depend on docling-core / DoclingDocument.concatenate (heavy; shifts pages)
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from pypdf import PdfReader

# Absolute page provenance for HybridChunker / citations (not a blind page-break).
_PAGE_MARKER_RE = re.compile(r"<!--\s*page:\s*(\d+)\s*-->", re.IGNORECASE)
_DEFAULT_PAGE_BREAK = "\n\n<!-- page-break -->\n\n"


def pdf_page_count(path: str | Path) -> int:
    """Return page count for a local PDF via pypdf."""
    reader = PdfReader(str(path))
    return len(reader.pages)


def page_ranges(n_pages: int, pages_per_part: int) -> list[tuple[int, int]]:
    """
    Build inclusive 1-based page ranges of at most ``pages_per_part`` pages.

    Examples (threshold 40): 90 pages → [(1,40), (41,80), (81,90)].
    When ``pages_per_part < 1`` or ``n_pages < 1``, returns [] (caller skips split).
    """
    if n_pages < 1 or pages_per_part < 1:
        return []
    ranges: list[tuple[int, int]] = []
    start = 1
    while start <= n_pages:
        end = min(start + pages_per_part - 1, n_pages)
        ranges.append((start, end))
        start = end + 1
    return ranges


def should_split_pdf(*, n_pages: int, threshold: int) -> bool:
    """True when a local PDF should be converted by page ranges."""
    return threshold > 0 and n_pages > threshold


def _iter_page_nos(node: Any) -> list[int]:
    found: list[int] = []
    if isinstance(node, dict):
        for key, val in node.items():
            if key in ("page_no", "page") and isinstance(val, int):
                found.append(val)
            else:
                found.extend(_iter_page_nos(val))
    elif isinstance(node, list):
        for item in node:
            found.extend(_iter_page_nos(item))
    return found


def detect_page_offset(json_content: Any, *, range_start: int) -> int:
    """
    Offset to add so part pages match the absolute PDF range.

    Docling often renumbers each ``page_range`` slice from 1. When the slice
    starts after page 1, map local page *k* → *k + (range_start - 1)*.
    If provenance already uses absolute numbers (≥ range_start), offset is 0.
    """
    if range_start <= 1 or json_content is None:
        return 0
    pages = _iter_page_nos(json_content)
    if not pages:
        return range_start - 1
    minimum = min(pages)
    if minimum >= range_start:
        return 0
    return range_start - 1


def apply_page_offset(node: Any, offset: int) -> Any:
    """
    Recursively add ``offset`` to page_no / page fields and ``pages`` map keys.

    Lightweight equivalent of the Docling ``_max_page`` / remapping step used
    before concatenate — keeps absolute source page numbers without docling-core.
    """
    if offset == 0 or node is None:
        return node
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, val in node.items():
            if key in ("page_no", "page") and isinstance(val, int):
                out[key] = val + offset
            elif key == "pages" and isinstance(val, dict):
                remapped: dict[Any, Any] = {}
                for pk, pv in val.items():
                    new_pv = apply_page_offset(pv, offset)
                    if isinstance(pk, int) or (isinstance(pk, str) and pk.isdigit()):
                        remapped[type(pk)(int(pk) + offset)] = new_pv
                    else:
                        remapped[pk] = new_pv
                out[key] = remapped
            else:
                out[key] = apply_page_offset(val, offset)
        return out
    if isinstance(node, list):
        return [apply_page_offset(item, offset) for item in node]
    return node


def remap_part_json(json_content: Any, *, range_start: int) -> Any:
    """Apply detected offset so a part's json_content uses absolute page numbers."""
    offset = detect_page_offset(json_content, range_start=range_start)
    return apply_page_offset(json_content, offset)


def _remap_inline_page_markers(text: str, *, offset: int) -> str:
    if offset == 0 or not text:
        return text

    def _sub(match: re.Match[str]) -> str:
        local = int(match.group(1))
        return f"<!-- page: {local + offset} -->"

    return _PAGE_MARKER_RE.sub(_sub, text)


def merge_part_markdown(
    parts: Sequence[tuple[int, int, str]],
    *,
    page_break: str = _DEFAULT_PAGE_BREAK,
    local_page_offset: bool = True,
) -> str:
    """
    Merge markdown from ordered page-range parts, preserving absolute pages.

    Each item is ``(range_start, range_end, md_text)``. Injects
    ``<!-- page: {start} -->`` at the head of each part and remaps any local
    ``<!-- page: k -->`` markers inside the body when ``local_page_offset``.
    """
    blocks: list[str] = []
    for start, _end, text in parts:
        body = (text or "").strip()
        offset = (start - 1) if local_page_offset and start > 1 else 0
        if offset:
            body = _remap_inline_page_markers(body, offset=offset)
        header = f"<!-- page: {start} -->"
        blocks.append(f"{header}\n\n{body}" if body else header)
    return page_break.join(blocks).strip()


def merge_part_json_contents(
    parts: Sequence[tuple[int, int, Any]],
) -> list[dict[str, Any]]:
    """
    Remap and collect json_content dicts with absolute page numbers.

    Returns a list (not a fake concatenate) so callers can keep provenance
    without depending on DoclingDocument.
    """
    merged: list[dict[str, Any]] = []
    for start, end, content in parts:
        if content is None:
            continue
        remapped = remap_part_json(content, range_start=start)
        if isinstance(remapped, dict):
            merged.append(
                {
                    "page_range": [start, end],
                    "json_content": remapped,
                }
            )
        else:
            merged.append({"page_range": [start, end], "json_content": remapped})
    return merged


def extract_json_content(data: dict[str, Any] | None) -> Any:
    """Pull json_content from a Docling Serve convert response, if present."""
    if not isinstance(data, dict):
        return None
    doc = data.get("document")
    if isinstance(doc, dict) and "json_content" in doc:
        return doc.get("json_content")
    documents = data.get("documents")
    if isinstance(documents, list):
        for item in documents:
            if isinstance(item, dict) and "json_content" in item:
                return item.get("json_content")
    return data.get("json_content")


@dataclass(frozen=True)
class PartCache:
    """Optional on-disk cache for per-range Docling convert payloads."""

    root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", Path(self.root))

    @staticmethod
    def file_digest(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()[:24]

    def part_path(self, *, digest: str, start: int, end: int) -> Path:
        return self.root / f"{digest}_p{start}-{end}.json"

    def load(self, *, digest: str, start: int, end: int) -> dict[str, Any] | None:
        path = self.part_path(digest=digest, start=start, end=end)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def store(self, *, digest: str, start: int, end: int, payload: dict[str, Any]) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.part_path(digest=digest, start=start, end=end)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path
