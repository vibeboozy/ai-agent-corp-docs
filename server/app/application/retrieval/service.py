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
from typing import Any

from app.adapters.embeddings.port import EmbeddingsClient
from app.adapters.llm.port import LLMClient
from app.adapters.vectorstore.port import VectorStore


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
        final_k = min(limit, self._rerank_top_k) if self._rerank_top_k else limit
        fetch_n = self._prefetch
        if self._rerank_mode == "llm":
            fetch_n = max(self._prefetch, self._rerank_candidates)

        vectors = await self._embeddings.embed_dense([query])
        dense = vectors[0] if vectors else None
        hits = await self._vectorstore.search(
            query, limit=min(fetch_n, max(fetch_n, final_k)), dense_vector=dense
        )
        hits = self._prefer_sort(list(hits or []))

        if self._rerank_mode == "llm":
            pool = hits[: self._rerank_candidates]
            hits = await self._llm_rerank(query, pool)

        hits = [
            h for h in hits if float(h.get("score") or 0.0) >= self._rerank_min_score
        ]
        hits = self._cap_per_doc(hits)
        return hits[:final_k]
