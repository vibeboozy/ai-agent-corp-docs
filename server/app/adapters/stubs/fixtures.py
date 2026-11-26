"""
ANCHOR: app.adapters.stubs.fixtures
PURPOSE: Deterministic regulation fixture corpus for stub retrieval/demo (ANC-STUB-02).
Dependencies: none
DO:
- Cover grounded hit, ambiguous multi-hit, empty hit
DONT:
- Require network or filesystem corpus for stub demos
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FixtureChunk:
    document_id: str
    chunk_id: str
    text: str
    document_title: str
    keywords: list[str]
    locator: str | None = None
    source: str = "fixture"  # fixture | learned
    metadata: dict[str, Any] = field(default_factory=dict)


# Seed regulations for prototype criteria 1–2.
_SEED_CHUNKS: list[FixtureChunk] = [
    FixtureChunk(
        document_id="reg-procurement-01",
        chunk_id="chunk-proc-sign",
        text=(
            "Договоры на закупку товаров и услуг подписывает директор по закупкам "
            "либо лицо, уполномоченное приказом генерального директора."
        ),
        document_title="Регламент закупок",
        keywords=["закупк", "договор", "подпис", "товар", "услуг"],
        locator="§3.2",
    ),
    FixtureChunk(
        document_id="reg-procurement-01",
        chunk_id="chunk-proc-threshold",
        text=(
            "Закупки свыше 1 000 000 рублей требуют согласования юридического отдела "
            "до подписания договора."
        ),
        document_title="Регламент закупок",
        keywords=["закупк", "согласован", "юридическ", "миллион", "порог"],
        locator="§4.1",
    ),
    FixtureChunk(
        document_id="reg-contractor-01",
        chunk_id="chunk-contr-sign",
        text=(
            "Договоры с подрядчиками подписывает руководитель подразделения-заказчика "
            "после согласования сметы."
        ),
        document_title="Регламент работы с подрядчиками",
        keywords=["подрядчик", "договор", "подпис", "смет"],
        locator="§2.1",
    ),
    FixtureChunk(
        document_id="reg-vacation-01",
        chunk_id="chunk-vac-approve",
        text=(
            "Заявление на ежегодный отпуск согласовывает непосредственный руководитель; "
            "кадровая служба оформляет приказ."
        ),
        document_title="Регламент отпусков",
        keywords=["отпуск", "заявлен", "кадр", "приказ"],
        locator="§1.3",
    ),
]


class FixtureKB:
    """Mutable in-process KB used by StubVectorStore and learning ingest."""

    def __init__(self) -> None:
        self._chunks: list[FixtureChunk] = deepcopy(_SEED_CHUNKS)

    def reset(self) -> None:
        self._chunks = deepcopy(_SEED_CHUNKS)

    def all_chunks(self) -> list[FixtureChunk]:
        return list(self._chunks)

    def upsert(self, chunk: FixtureChunk) -> None:
        self._chunks = [c for c in self._chunks if c.chunk_id != chunk.chunk_id]
        self._chunks.append(chunk)

    def search(self, query: str, *, limit: int = 5) -> list[tuple[FixtureChunk, float]]:
        q = query.lower()
        scored: list[tuple[FixtureChunk, float]] = []
        for chunk in self._chunks:
            hits = sum(1 for kw in chunk.keywords if kw.lower() in q)
            # Also score token overlap with chunk text lightly
            text_l = chunk.text.lower()
            tokens = [t for t in q.replace("?", " ").split() if len(t) > 3]
            token_hits = sum(1 for t in tokens if t in text_l)
            score = hits * 1.0 + token_hits * 0.2
            if score > 0:
                scored.append((chunk, min(score / max(len(chunk.keywords), 1), 1.0)))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]


# Process-wide default KB so learning persists across stub container rebuilds in one process.
SHARED_FIXTURE_KB = FixtureKB()
