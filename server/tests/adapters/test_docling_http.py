"""
ANCHOR: tests.adapters.test_docling_http
PURPOSE: Docling Serve 1.26 /v1/convert/source body shape (mocked HTTP).
Dependencies: app.adapters.docling.http
"""

from __future__ import annotations

import base64
from pathlib import Path

import httpx
import pytest

from app.adapters.docling.http import HttpDoclingClient


@pytest.mark.asyncio
async def test_http_docling_posts_v1_file_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = tmp_path / "reg.docx"
    doc.write_bytes(b"PK\x03\x04fake-docx")

    captured: dict = {}

    class _Resp:
        status_code = 200
        text = ""

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"document": {"md_content": "Статья 1. Текст регламента."}}

    class _Client:
        def __init__(self, *a, **k) -> None:
            pass

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *a) -> None:
            return None

        async def post(self, url: str, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _Resp()

        async def get(self, url: str, headers=None):
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    client = HttpDoclingClient(base_url="http://docling.local:5001", api_key="k")
    result = await client.convert(source_path=str(doc))

    assert captured["url"] == "http://docling.local:5001/v1/convert/source"
    sources = captured["json"]["sources"]
    assert len(sources) == 1
    assert sources[0]["kind"] == "file"
    assert sources[0]["filename"] == "reg.docx"
    assert sources[0]["base64_string"] == base64.b64encode(doc.read_bytes()).decode("ascii")
    opts = captured["json"]["options"]
    assert opts["do_ocr"] is True
    assert "ru" in opts["ocr_lang"]
    assert "md_page_break_placeholder" in opts
    assert result["chunks"]
    assert "регламента" in result["chunks"][0]["text"].lower()
    assert result["chunker"] == "HybridChunker"


@pytest.mark.asyncio
async def test_http_docling_http_source(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class _Resp:
        status_code = 200
        text = ""

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"document": {"text_content": "remote text"}}

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
    client = HttpDoclingClient(base_url="http://docling.local:5001", api_key=None)
    await client.convert(source_path="https://example.com/a.pdf")
    assert captured["json"]["sources"] == [{"kind": "http", "url": "https://example.com/a.pdf"}]


@pytest.mark.asyncio
async def test_http_docling_text_as_file_source(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class _Resp:
        status_code = 200
        text = ""

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"document": {"md_content": "from-text"}}

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
    client = HttpDoclingClient(base_url="http://docling.local:5001", api_key=None)
    await client.convert(text="hello officer")
    src = captured["json"]["sources"][0]
    assert src["kind"] == "file"
    assert src["filename"] == "inline.txt"
    assert base64.b64decode(src["base64_string"]).decode("utf-8") == "hello officer"
