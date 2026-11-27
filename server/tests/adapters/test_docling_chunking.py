"""
ANCHOR: tests.adapters.test_docling_chunking
PURPOSE: HybridChunker-style windowing from DOCLING_CHUNK_* (offline).
Dependencies: app.adapters.docling.http.hybrid_chunk_text
"""

from __future__ import annotations

from app.adapters.docling.http import hybrid_chunk_text


def test_hybrid_chunk_respects_max_and_overlap() -> None:
    words = [f"w{i}" for i in range(100)]
    body = " ".join(words)
    out = hybrid_chunk_text(
        body,
        max_tokens=20,
        overlap_tokens=5,
        min_tokens=5,
        chunker="HybridChunker",
        tokenizer="BAAI/bge-m3",
    )
    assert out["chunker"] == "HybridChunker"
    assert out["tokenizer"] == "BAAI/bge-m3"
    assert len(out["chunks"]) >= 5
    assert all(c["token_count"] <= 20 for c in out["chunks"])
    # Overlap: next chunk starts before previous ends
    first = out["chunks"][0]["text"].split()
    second = out["chunks"][1]["text"].split()
    assert first[-5:] == second[:5]


def test_hybrid_chunk_short_text_single_chunk() -> None:
    out = hybrid_chunk_text("один два три", max_tokens=512, min_tokens=1)
    assert len(out["chunks"]) == 1
    assert "один" in out["chunks"][0]["text"]


def test_hybrid_chunk_section_aware_keeps_clause_boundaries() -> None:
    body = (
        "7.1. Общие положения. Текст раздела семь один про организацию.\n\n"
        "7.2. Планирование поставок. "
        "7.2.1. За планирование поставок отвечает Менеджер по поставке, "
        "при его отсутствии – АМ.\n\n"
        "17.3. Исполнители команды проекта выполняют работы "
        "в соответствии с утвержденным календарным план-графиком работ."
    )
    out = hybrid_chunk_text(body, max_tokens=40, overlap_tokens=5, min_tokens=5)
    texts = [c["text"] for c in out["chunks"]]
    # Section 7.2 should appear as its own (or starting) chunk — not glued after 17.x remnant.
    supply = [t for t in texts if "Планирование поставок" in t or "планирование поставок" in t]
    assert supply, texts
    assert not any(t.lower().startswith("проекта.") for t in texts)
    # Locator/section_title populated for numbered sections.
    assert any(c.get("section_title") for c in out["chunks"])
