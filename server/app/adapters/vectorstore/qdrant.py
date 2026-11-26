"""
ANCHOR: app.adapters.vectorstore.qdrant
PURPOSE: QdrantVectorStore adapter behind QDRANT_USE_STUB=false.
Dependencies: qdrant-client (optional extra); Settings
"""

from __future__ import annotations

from typing import Any

from app.adapters.vectorstore.port import VectorStore
from app.domain.errors import AppError


class QdrantVectorStore:
    """Thin Qdrant wrapper — requires qdrant-client when used live."""

    def __init__(
        self,
        *,
        url: str,
        api_key: str | None,
        collection: str,
        timeout_s: float = 60.0,
        upsert_batch: int = 64,
    ) -> None:
        self._url = url
        self._api_key = api_key
        self._collection = collection
        self._timeout = timeout_s
        self._upsert_batch = upsert_batch
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from qdrant_client import QdrantClient
        except ImportError as exc:
            raise AppError(
                "qdrant-client not installed; pip install '.[vector]'",
                code="DEPENDENCY_MISSING",
            ) from exc
        self._client = QdrantClient(url=self._url, api_key=self._api_key, timeout=self._timeout)
        return self._client

    async def ping(self) -> bool:
        client = self._get_client()
        client.get_collections()
        return True

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
        dense_vector: list[float] | None = None,
    ) -> list[dict[str, Any]]:
        if dense_vector is None:
            raise AppError("dense_vector required for Qdrant search", code="VALIDATION_ERROR")
        client = self._get_client()
        # qdrant-client is sync; wrap call site keeps async signature stable.
        points = client.search(
            collection_name=self._collection,
            query_vector=dense_vector,
            limit=limit,
            with_payload=True,
        )
        out: list[dict[str, Any]] = []
        for p in points:
            payload = p.payload or {}
            out.append(
                {
                    "document_id": payload.get("document_id", ""),
                    "chunk_id": payload.get("chunk_id", str(p.id)),
                    "text": payload.get("text", ""),
                    "score": float(p.score or 0.0),
                    "document_title": payload.get("document_title"),
                    "locator": payload.get("locator"),
                    "source": payload.get("source", "qdrant"),
                    "metadata": payload,
                    "query": query,
                }
            )
        return out

    async def upsert(self, chunks: list[dict[str, Any]]) -> None:
        try:
            from qdrant_client.http import models as rest
        except ImportError as exc:
            raise AppError(
                "qdrant-client not installed; pip install '.[vector]'",
                code="DEPENDENCY_MISSING",
            ) from exc
        client = self._get_client()
        points = []
        for i, chunk in enumerate(chunks):
            vector = chunk.get("vector") or chunk.get("dense_vector")
            if vector is None:
                continue
            points.append(
                rest.PointStruct(
                    id=chunk.get("point_id") or chunk["chunk_id"],
                    vector=vector,
                    payload={
                        "document_id": chunk["document_id"],
                        "chunk_id": chunk["chunk_id"],
                        "text": chunk["text"],
                        "document_title": chunk.get("document_title"),
                        "locator": chunk.get("locator"),
                        "source": chunk.get("source", "ingest"),
                        "metadata": chunk.get("metadata") or {},
                    },
                )
            )
            if len(points) >= self._upsert_batch:
                client.upsert(collection_name=self._collection, points=points)
                points = []
        if points:
            client.upsert(collection_name=self._collection, points=points)
        _ = i


_: VectorStore = QdrantVectorStore(  # type: ignore[assignment]
    url="http://127.0.0.1:6333",
    api_key=None,
    collection="corp_regs",
)
