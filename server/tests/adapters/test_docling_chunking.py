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
    out = hybrid_chunk_text("один два три", max_tokens=512, min_tokens=32)
    assert len(out["chunks"]) == 1
    assert "один" in out["chunks"][0]["text"]
