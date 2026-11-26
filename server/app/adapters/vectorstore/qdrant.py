"""
ANCHOR: app.adapters.vectorstore.qdrant
PURPOSE: QdrantVectorStore adapter behind QDRANT_USE_STUB=false.
Dependencies: qdrant-client (optional extra); Settings
CRITICAL: Auto-create collection (bge-m3 1024) before search/upsert; use query_points.
DO:
- Stable UUID5 point ids from chunk_id
- Ensure collection exists before mutating/querying
DONT:
- Use deprecated client.search
"""

from __future__ import annotations

import uuid
from typing import Any

from app.adapters.vectorstore.port import VectorStore
from app.domain.errors import AppError

# Namespace for deterministic point ids (chunk_id → UUID).
_POINT_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def _point_id(raw: str | int | None, *, fallback: str) -> str | int:
    """Qdrant accepts UUID or unsigned int — never arbitrary strings."""
    if isinstance(raw, int) and raw >= 0:
        return raw
    text = str(raw) if raw is not None else fallback
    try:
        return str(uuid.UUID(text))
    except (ValueError, AttributeError, TypeError):
        return str(uuid.uuid5(_POINT_NS, text))


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
        vector_size: int = 1024,
    ) -> None:
        self._url = url
        self._api_key = api_key
        self._collection = collection
        self._timeout = timeout_s
        self._upsert_batch = upsert_batch
        self._vector_size = vector_size
        self._client: Any = None
        self._collection_ready = False

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

    def _ensure_collection(self) -> None:
        """Create the collection if missing (dense bge-m3 / configured size)."""
        if self._collection_ready:
            return
        try:
            from qdrant_client.http import models as rest
        except ImportError as exc:
            raise AppError(
                "qdrant-client not installed; pip install '.[vector]'",
                code="DEPENDENCY_MISSING",
            ) from exc
        client = self._get_client()
        names = {c.name for c in client.get_collections().collections}
        if self._collection not in names:
            client.create_collection(
                collection_name=self._collection,
                vectors_config=rest.VectorParams(
                    size=self._vector_size,
                    distance=rest.Distance.COSINE,
                ),
            )
        self._collection_ready = True

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
        self._ensure_collection()
        client = self._get_client()
        # Prefer query_points (search is deprecated in recent qdrant-client).
        result = client.query_points(
            collection_name=self._collection,
            query=dense_vector,
            limit=limit,
            with_payload=True,
        )
        points = getattr(result, "points", None) or result or []
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
        self._ensure_collection()
        client = self._get_client()
        points = []
        for chunk in chunks:
            vector = chunk.get("vector") or chunk.get("dense_vector")
            if vector is None:
                continue
            chunk_id = str(chunk.get("chunk_id") or "")
            pid = _point_id(
                chunk.get("point_id"),
                fallback=chunk_id or f"anon-{len(points)}",
            )
            points.append(
                rest.PointStruct(
                    id=pid,
                    vector=vector,
                    payload={
                        "document_id": chunk["document_id"],
                        "chunk_id": chunk_id,
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


_: VectorStore = QdrantVectorStore(  # type: ignore[assignment]
    url="http://127.0.0.1:6333",
    api_key=None,
    collection="corp_regs",
)
