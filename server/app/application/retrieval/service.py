"""
ANCHOR: app.application.retrieval.service
PURPOSE: Hybrid retrieval + optional LLM rerank before answer context.
Dependencies: embeddings port, vectorstore port, optional LLMClient
DO:
- Prefetch candidates then rerank (RERANK_MODE=llm) or pass-through (none)
- Prefer latest / learned chunks when configured
DONT:
- Return answers — retrieval only yields candidates
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from app.adapters.embeddings.port import EmbeddingsClient
from app.adapters.llm.port import LLMClient
from app.adapters.vectorstore.port import VectorStore


@dataclass
class RetrievalResult:
    """Hits plus timing / rerank metadata for audit_events."""

    hits: list[dict[str, Any]]
    rerank_mode: str = "none"
    latency_ms: dict[str, float] = field(default_factory=dict)
    rerank_scores: list[dict[str, Any]] = field(default_factory=list)


class RetrievalService:
    def __init__(
        self,
        *,
        embeddings: EmbeddingsClient,
        vectorstore: VectorStore,
        prefetch: int = 50,
        prefer_latest: bool = True,
        rerank_mode: str = "none",
        rerank_candidates: int = 20,
        rerank_top_k: int = 5,
        rerank_max_per_doc: int = 3,
        rerank_min_score: float = 0.0,
        llm: LLMClient | None = None,
        rerank_llm_model: str | None = None,
    ) -> None:
        self._embeddings = embeddings
        self._vectorstore = vectorstore
        self._prefetch = prefetch
        self._prefer_latest = prefer_latest
        self._rerank_mode = (rerank_mode or "none").lower()
        self._rerank_candidates = max(1, int(rerank_candidates))
        self._rerank_top_k = max(1, int(rerank_top_k))
        self._rerank_max_per_doc = max(1, int(rerank_max_per_doc))
        self._rerank_min_score = float(rerank_min_score)
        self._llm = llm
        self._rerank_llm_model = rerank_llm_model

    def _prefer_sort(self, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not self._prefer_latest:
            return hits
        return sorted(
            hits,
            key=lambda h: (
                1 if h.get("source") == "learned" else 0,
                float(h.get("score") or 0.0),
            ),
            reverse=True,
        )

    def _cap_per_doc(self, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        out: list[dict[str, Any]] = []
        for hit in hits:
            doc_id = str(hit.get("document_id") or "")
            counts[doc_id] = counts.get(doc_id, 0) + 1
            if counts[doc_id] <= self._rerank_max_per_doc:
                out.append(hit)
        return out

    async def _llm_rerank(
        self, query: str, hits: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if not self._llm or not hits:
            return hits
        lines = []
        for idx, hit in enumerate(hits):
            snippet = str(hit.get("text") or "")[:400]
            lines.append(f"[{idx}] {snippet}")
        prompt = (
            "Rank passages by relevance to the user question. "
            "Reply with a comma-separated list of indices best-first only.\n"
            f"Question: {query}\n"
            "Passages:\n" + "\n".join(lines)
        )
        # Optional model override is advisory — HttpLLMClient uses Settings model;
        # include hint in system so providers that honor it can switch.
        system = "Reranker"
        if self._rerank_llm_model:
            system = f"Reranker model_hint={self._rerank_llm_model}"
        raw = await self._llm.complete(system=system, user=prompt, temperature=0.0)
        indices = [int(x) for x in re.findall(r"\d+", raw or "")]
        seen: set[int] = set()
        ordered: list[dict[str, Any]] = []
        n = len(hits)
        for i in indices:
            if 0 <= i < n and i not in seen:
                seen.add(i)
                hit = dict(hits[i])
                # Rank-derived score in [0,1]
                hit["score"] = max(
                    float(hit.get("score") or 0.0),
                    1.0 - (len(ordered) / max(1, n)),
                )
                ordered.append(hit)
        for i, hit in enumerate(hits):
            if i not in seen:
                ordered.append(dict(hit))
        return ordered

    async def retrieve(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        """Return ranked hits only (compat). Prefer retrieve_with_meta for audit."""
        return (await self.retrieve_with_meta(query, limit=limit)).hits

    async def retrieve_with_meta(self, query: str, *, limit: int = 5) -> RetrievalResult:
        """Hybrid search + optional LLM rerank; includes latency and score trail."""
        final_k = min(limit, self._rerank_top_k) if self._rerank_top_k else limit
        fetch_n = self._prefetch
        if self._rerank_mode == "llm":
            fetch_n = max(self._prefetch, self._rerank_candidates)

        t0 = time.perf_counter()
        vectors = await self._embeddings.embed_dense([query])
        sparse_maps = await self._embeddings.embed_sparse([query])
        embed_ms = round((time.perf_counter() - t0) * 1000, 2)
        dense = vectors[0] if vectors else None
        sparse = sparse_maps[0] if sparse_maps else None

        t1 = time.perf_counter()
        hits = await self._vectorstore.search(
            query,
            limit=min(fetch_n, max(fetch_n, final_k)),
            dense_vector=dense,
            sparse_vector=sparse,
        )
        search_ms = round((time.perf_counter() - t1) * 1000, 2)
        hits = self._prefer_sort(list(hits or []))

        rerank_ms = 0.0
        if self._rerank_mode == "llm":
            pool = hits[: self._rerank_candidates]
            t2 = time.perf_counter()
            hits = await self._llm_rerank(query, pool)
            rerank_ms = round((time.perf_counter() - t2) * 1000, 2)

        hits = [
            h for h in hits if float(h.get("score") or 0.0) >= self._rerank_min_score
        ]
        hits = self._cap_per_doc(hits)
        final = hits[:final_k]
        latency: dict[str, float] = {
            "retrieval_total_ms": round((time.perf_counter() - t0) * 1000, 2),
            "embed_ms": embed_ms,
            "search_ms": search_ms,
        }
        if self._rerank_mode == "llm":
            latency["rerank_ms"] = rerank_ms
        scores = [
            {
                "chunk_id": str(h.get("chunk_id") or ""),
                "document_id": str(h.get("document_id") or ""),
                "score": float(h.get("score") or 0.0),
            }
            for h in final
        ]
        return RetrievalResult(
            hits=final,
            rerank_mode=self._rerank_mode,
            latency_ms=latency,
            rerank_scores=scores,
        )
