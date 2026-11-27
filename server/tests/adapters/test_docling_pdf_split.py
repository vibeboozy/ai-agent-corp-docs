"""
ANCHOR: tests.adapters.test_docling_pdf_split
PURPOSE: Unit tests for page_ranges / merge / page-offset helpers (no live Docling).
Dependencies: app.adapters.docling.pdf_split; pypdf for tiny fixture PDFs
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from pypdf import PdfWriter

from app.adapters.docling.http import HttpDoclingClient
from app.adapters.docling.pdf_split import (
    PartCache,
    apply_page_offset,
    detect_page_offset,
    merge_part_json_contents,
    merge_part_markdown,
    page_ranges,
    pdf_page_count,
    remap_part_json,
    should_split_pdf,
)


def _write_blank_pdf(path: Path, n_pages: int) -> Path:
    writer = PdfWriter()
    for _ in range(n_pages):
        writer.add_blank_page(width=72, height=72)
    with path.open("wb") as fh:
        writer.write(fh)
    return path


def test_page_ranges_default_threshold() -> None:
    assert page_ranges(40, 40) == [(1, 40)]
    assert page_ranges(41, 40) == [(1, 40), (41, 41)]
    assert page_ranges(90, 40) == [(1, 40), (41, 80), (81, 90)]
    assert page_ranges(1, 40) == [(1, 1)]
    assert page_ranges(0, 40) == []
    assert page_ranges(100, 0) == []


def test_should_split_pdf() -> None:
    assert should_split_pdf(n_pages=41, threshold=40) is True
    assert should_split_pdf(n_pages=40, threshold=40) is False
    assert should_split_pdf(n_pages=100, threshold=0) is False


def test_pdf_page_count(tmp_path: Path) -> None:
    pdf = _write_blank_pdf(tmp_path / "n.pdf", 7)
    assert pdf_page_count(pdf) == 7


def test_merge_part_markdown_preserves_absolute_pages() -> None:
    merged = merge_part_markdown(
        [
            (1, 40, "Part A page-local <!-- page: 2 --> text"),
            (41, 80, "Part B local <!-- page: 1 --> more"),
            (81, 90, "Part C"),
        ]
    )
    assert "<!-- page: 1 -->" in merged
    assert "<!-- page: 41 -->" in merged
    assert "<!-- page: 81 -->" in merged
    # Local markers inside later parts are remapped to absolute pages.
    assert "Part B local <!-- page: 41 -->" in merged  # local 1 + (41-1)
    assert "Part A page-local <!-- page: 2 -->" in merged  # offset 0
    assert "<!-- page-break -->" in merged
    assert "Part A" in merged and "Part C" in merged


def test_detect_and_apply_page_offset() -> None:
    local = {
        "pages": {"1": {"page_no": 1}, "2": {"page_no": 2}},
        "texts": [{"prov": [{"page_no": 1}]}],
    }
    assert detect_page_offset(local, range_start=41) == 40
    remapped = apply_page_offset(local, 40)
    assert remapped["pages"]["41"]["page_no"] == 41
    assert remapped["pages"]["42"]["page_no"] == 42
    assert remapped["texts"][0]["prov"][0]["page_no"] == 41

    absolute = {"texts": [{"prov": [{"page_no": 41}]}]}
    assert detect_page_offset(absolute, range_start=41) == 0


def test_remap_part_json_and_merge_list() -> None:
    part_a = {"pages": {"1": {"page_no": 1}}, "body": "a"}
    part_b = {"pages": {"1": {"page_no": 1}}, "body": "b"}
    assert remap_part_json(part_a, range_start=1)["pages"]["1"]["page_no"] == 1
    merged = merge_part_json_contents(
        [
            (1, 40, part_a),
            (41, 80, part_b),
        ]
    )
    assert len(merged) == 2
    assert merged[0]["page_range"] == [1, 40]
    assert merged[1]["json_content"]["pages"]["41"]["page_no"] == 41


def test_part_cache_roundtrip(tmp_path: Path) -> None:
    cache = PartCache(tmp_path / "parts")
    digest = "abc123"
    payload = {"text": "hello", "raw": {"document": {"md_content": "hello"}}}
    cache.store(digest=digest, start=1, end=40, payload=payload)
    loaded = cache.load(digest=digest, start=1, end=40)
    assert loaded == payload
    assert cache.load(digest=digest, start=41, end=80) is None


@pytest.mark.asyncio
async def test_http_docling_splits_large_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _write_blank_pdf(tmp_path / "big.pdf", 5)
    calls: list[dict] = []

    class _Resp:
        status_code = 200
        text = ""

        def __init__(self, start: int, end: int) -> None:
            self._start = start
            self._end = end

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "document": {
                    "md_content": f"pages {self._start}-{self._end}",
                    "json_content": {
                        "pages": {
                            str(i - self._start + 1): {"page_no": i - self._start + 1}
                            for i in range(self._start, self._end + 1)
                        }
                    },
                }
            }

    class _Client:
        def __init__(self, *a, **k) -> None:
            pass

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *a) -> None:
            return None

        async def post(self, url: str, headers=None, json=None):
            calls.append(json)
            pr = json["options"]["page_range"]
            return _Resp(pr[0], pr[1])

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    client = HttpDoclingClient(
        base_url="http://docling.local:5001",
        api_key=None,
        pdf_split_pages=2,
        pdf_part_cache_dir=str(tmp_path / "cache"),
    )
    result = await client.convert(source_path=str(pdf))

    assert len(calls) == 3  # (1,2), (3,4), (5,5)
    assert sorted(c["options"]["page_range"] for c in calls) == [[1, 2], [3, 4], [5, 5]]
    assert result["pdf_split"]["n_pages"] == 5
    assert result["pdf_split"]["parts"] == 3
    assert "<!-- page: 1 -->" in result["text"]
    assert "<!-- page: 3 -->" in result["text"]
    assert "<!-- page: 5 -->" in result["text"]
    assert result["chunks"]

    # Second convert should hit part cache (no new HTTP posts).
    calls.clear()
    result2 = await client.convert(source_path=str(pdf))
    assert calls == []
    assert result2["pdf_split"]["parts"] == 3


@pytest.mark.asyncio
async def test_http_docling_skips_split_under_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _write_blank_pdf(tmp_path / "small.pdf", 3)
    captured: dict = {}

    class _Resp:
        status_code = 200
        text = ""

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"document": {"md_content": "small pdf"}}

    class _Client:
        def __init__(self, *a, **k) -> None:
            pass

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *a) -> None:
            return None

        async def post(self, url: str, headers=None, json=None):
            captured["json"] = json
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    client = HttpDoclingClient(
        base_url="http://docling.local:5001",
        api_key=None,
        pdf_split_pages=40,
    )
    result = await client.convert(source_path=str(pdf))
    assert "page_range" not in captured["json"]["options"]
    assert "pdf_split" not in result
