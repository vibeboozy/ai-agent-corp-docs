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


def test_hybrid_chunk_merges_tiny_titled_sections() -> None:
    """Few-word titled clauses must not become standalone context-poor chunks."""
    body = (
        "3.1. Согласование.\n\n"
        "3.2. Директора бюджета.\n\n"
        "4.2. Пороговая маржинальность. В Дирекции ИБ установлен точный процент "
        "пороговой маржинальности равный пятнадцати процентам от стоимости проекта "
        "при оценке коммерческих предложений и расчёте рентабельности сделок."
    )
    out = hybrid_chunk_text(body, max_tokens=80, overlap_tokens=8, min_tokens=20)
    chunks = out["chunks"]
    assert chunks
    # No few-word orphan chunks.
    assert all(c["token_count"] >= 20 or c is chunks[-1] for c in chunks)
    tinyish = [c for c in chunks if c["token_count"] < 8]
    assert not tinyish, chunks
    # Tiny 3.1 / 3.2 content survived by merging into a neighbor.
    joined = " ".join(c["text"] for c in chunks)
    assert "маржинальность" in joined.lower()


def test_hybrid_chunk_merge_rewindows_to_max_tokens() -> None:
    """Repeated tiny-section merges must not emit unbounded chunks (PR #20 regression)."""
    parts = ["## 1. Введение\n" + " ".join(f"слово{i}" for i in range(400))]
    for i in range(2, 200):
        parts.append(f"{i}. короткий фрагмент номер {i}.")
    body = "\n\n".join(parts)
    out = hybrid_chunk_text(body, max_tokens=512, overlap_tokens=64, min_tokens=48)
    chunks = out["chunks"]
    assert chunks
    assert all(c["token_count"] <= 512 for c in chunks), max(c["token_count"] for c in chunks)
    # Tiny fragment content survived (re-windowed, not dropped).
    joined = " ".join(c["text"] for c in chunks)
    assert "короткий фрагмент номер 2" in joined
    assert "короткий фрагмент номер 199" in joined
    assert len(chunks) >= 2
