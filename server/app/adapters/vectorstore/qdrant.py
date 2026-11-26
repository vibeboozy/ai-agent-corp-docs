"""
ANCHOR: app.adapters.vectorstore.qdrant
PURPOSE: QdrantVectorStore live adapter — named dense + sparse hybrid.
Dependencies: qdrant-client (optional extra); Settings
CRITICAL: Collection MUST use named vectors `dense` + `sparse` (not unnamed Default).
DO:
- Stable UUID5 point ids from chunk_id
- Ensure hybrid collection schema before search/upsert; recreate if wrong schema
- Hybrid query via Prefetch + RRF Fusion (Qdrant 1.19+)
DONT:
- Use deprecated client.search
- Upsert unnamed/default vectors into a named-vector collection (indexed_vectors_count=0)
"""

from __future__ import annotations

import uuid
import zlib
from typing import Any

from app.adapters.vectorstore.port import VectorStore
from app.domain.errors import AppError

# Namespace for deterministic point ids (chunk_id → UUID).
_POINT_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"


def _point_id(raw: str | int | None, *, fallback: str) -> str | int:
    """Qdrant accepts UUID or unsigned int — never arbitrary strings."""
    if isinstance(raw, int) and raw >= 0:
        return raw
    text = str(raw) if raw is not None else fallback
    try:
        return str(uuid.UUID(text))
    except (ValueError, AttributeError, TypeError):
        return str(uuid.uuid5(_POINT_NS, text))


def sparse_weights_to_vector(weights: dict[str, float] | None) -> dict[str, list]:
    """
    Map token→weight (or index→weight) dict to Qdrant SparseVector.

    - Accepts already-shaped {"indices": [...], "values": [...]}
    - Dedupes CRC32 collisions by summing weights (Qdrant requires unique indices)
    - Skips non-finite / non-numeric weights
    """
    if not weights:
        return {"indices": [], "values": []}
    if "indices" in weights and "values" in weights:
        raw_idx = list(weights.get("indices") or [])  # type: ignore[arg-type]
        raw_val = list(weights.get("values") or [])  # type: ignore[arg-type]
        merged: dict[int, float] = {}
        for idx, val in zip(raw_idx, raw_val, strict=False):
            try:
                i = int(idx) & 0x7FFFFFFF
                v = float(val)
            except (TypeError, ValueError):
                continue
            if v != v:  # NaN
                continue
            merged[i] = merged.get(i, 0.0) + v
        indices = list(merged.keys())
        values = [merged[i] for i in indices]
        return {"indices": indices, "values": values}

    merged_tok: dict[int, float] = {}
    for token, weight in weights.items():
        try:
            v = float(weight)
        except (TypeError, ValueError):
            continue
        if v != v:
            continue
        # Numeric string keys from sparse API indices → use directly.
        try:
            idx = int(str(token)) & 0x7FFFFFFF
        except ValueError:
            idx = zlib.crc32(str(token).encode("utf-8")) & 0x7FFFFFFF
        merged_tok[idx] = merged_tok.get(idx, 0.0) + v
    indices = list(merged_tok.keys())
    values = [merged_tok[i] for i in indices]
    return {"indices": indices, "values": values}


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

    def _schema_is_hybrid(self, client: Any) -> bool:
        """True when collection has named dense + sparse vectors (not unnamed Default)."""
        try:
            info = client.get_collection(self._collection)
        except Exception:
            return False
        params = getattr(info, "config", None)
        params = getattr(params, "params", params)
        vectors = getattr(params, "vectors", None) if params is not None else None
        sparse = getattr(params, "sparse_vectors", None) if params is not None else None
        # Named dense: vectors is a dict-like with DENSE_VECTOR_NAME.
        if isinstance(vectors, dict):
            has_dense = DENSE_VECTOR_NAME in vectors
        else:
            # Unnamed / "Default" VectorParams — wrong for hybrid.
            has_dense = False
        has_sparse = False
        if isinstance(sparse, dict):
            has_sparse = SPARSE_VECTOR_NAME in sparse
        return bool(has_dense and has_sparse)

    def _create_hybrid_collection(self, client: Any, rest: Any) -> None:
        client.create_collection(
            collection_name=self._collection,
            vectors_config={
                DENSE_VECTOR_NAME: rest.VectorParams(
                    size=self._vector_size,
                    distance=rest.Distance.COSINE,
                )
            },
            sparse_vectors_config={
                SPARSE_VECTOR_NAME: rest.SparseVectorParams(
                    index=rest.SparseIndexParams(on_disk=False),
                )
            },
        )

    def _ensure_collection(self) -> None:
        """Create or recreate collection with named dense + sparse (Qdrant 1.19)."""
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
        if self._collection in names:
            if not self._schema_is_hybrid(client):
                # Wrong schema (e.g. unnamed Default 1024) → indexed hybrid count stays 0.
                client.delete_collection(collection_name=self._collection)
                self._create_hybrid_collection(client, rest)
        else:
            self._create_hybrid_collection(client, rest)
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
        sparse_vector: dict[str, float] | None = None,
    ) -> list[dict[str, Any]]:
        if dense_vector is None:
            raise AppError("dense_vector required for Qdrant search", code="VALIDATION_ERROR")
        try:
            from qdrant_client.http import models as rest
        except ImportError as exc:
            raise AppError(
                "qdrant-client not installed; pip install '.[vector]'",
                code="DEPENDENCY_MISSING",
            ) from exc
        self._ensure_collection()
        client = self._get_client()
        prefetch = [
            rest.Prefetch(
                query=dense_vector,
                using=DENSE_VECTOR_NAME,
                limit=max(limit, 20),
            )
        ]
        sparse_payload = sparse_weights_to_vector(sparse_vector)
        if sparse_payload["indices"]:
            prefetch.append(
                rest.Prefetch(
                    query=rest.SparseVector(
                        indices=sparse_payload["indices"],
                        values=sparse_payload["values"],
                    ),
                    using=SPARSE_VECTOR_NAME,
                    limit=max(limit, 20),
                )
            )
        # Hybrid RRF when sparse present; otherwise dense-only named query.
        if len(prefetch) > 1:
            result = client.query_points(
                collection_name=self._collection,
                prefetch=prefetch,
                query=rest.FusionQuery(fusion=rest.Fusion.RRF),
                limit=limit,
                with_payload=True,
            )
        else:
            result = client.query_points(
                collection_name=self._collection,
                query=dense_vector,
                using=DENSE_VECTOR_NAME,
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
            dense = chunk.get("vector") or chunk.get("dense_vector")
            if dense is None:
                continue
            sparse_raw = chunk.get("sparse_vector")
            if isinstance(sparse_raw, dict) and (
                "indices" in sparse_raw and "values" in sparse_raw
            ):
                sparse_payload = {
                    "indices": list(sparse_raw["indices"]),
                    "values": [float(v) for v in sparse_raw["values"]],
                }
            else:
                sparse_payload = sparse_weights_to_vector(
                    sparse_raw if isinstance(sparse_raw, dict) else None
                )
            chunk_id = str(chunk.get("chunk_id") or "")
            pid = _point_id(
                chunk.get("point_id"),
                fallback=chunk_id or f"anon-{len(points)}",
            )
            named_vectors: dict[str, Any] = {DENSE_VECTOR_NAME: dense}
            if sparse_payload["indices"]:
                named_vectors[SPARSE_VECTOR_NAME] = rest.SparseVector(
                    indices=sparse_payload["indices"],
                    values=sparse_payload["values"],
                )
            points.append(
                rest.PointStruct(
                    id=pid,
                    vector=named_vectors,
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
