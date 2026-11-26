"""
ANCHOR: tests.adapters.test_qdrant_adapter
PURPOSE: Unit tests for hybrid dense+sparse collection, query_points, UUID point ids.
Dependencies: app.adapters.vectorstore.qdrant (mocked client)
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.adapters.vectorstore.qdrant import (
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    QdrantVectorStore,
    _point_id,
    sparse_weights_to_vector,
)


def test_point_id_uuid5_for_string_chunk_ids() -> None:
    a = _point_id("chunk-abc", fallback="x")
    b = _point_id("chunk-abc", fallback="x")
    assert a == b
    assert isinstance(a, str)
    # Valid UUID string
    import uuid

    uuid.UUID(a)


def test_point_id_preserves_uuid_and_int() -> None:
    u = "43cf51e2-8777-4f52-bc74-c2cbde0c8b04"
    assert _point_id(u, fallback="x") == u
    assert _point_id(42, fallback="x") == 42


def test_sparse_weights_to_vector_stable() -> None:
    a = sparse_weights_to_vector({"отчетность": 1.0, "проект": 2.0})
    b = sparse_weights_to_vector({"отчетность": 1.0, "проект": 2.0})
    assert a["indices"] == b["indices"]
    assert a["values"] == b["values"]
    assert len(a["indices"]) == 2


def test_sparse_weights_dedupes_and_accepts_indices_shape() -> None:
    shaped = sparse_weights_to_vector({"indices": [5, 5, 9], "values": [1.0, 2.0, 3.0]})
    assert shaped["indices"].count(5) == 1
    assert shaped["values"][shaped["indices"].index(5)] == 3.0
    empty = sparse_weights_to_vector(None)
    assert empty == {"indices": [], "values": []}


class _FakeCollections:
    def __init__(self, names: list[str]) -> None:
        self.collections = [SimpleNamespace(name=n) for n in names]


class _FakeClient:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.deleted: list[str] = []
        self.queries: list[dict[str, Any]] = []
        self.upserts: list[dict[str, Any]] = []
        self._names: list[str] = []
        self._hybrid = False

    def get_collections(self) -> _FakeCollections:
        return _FakeCollections(self._names)

    def get_collection(self, name: str) -> Any:
        if self._hybrid:
            vectors = {DENSE_VECTOR_NAME: object(), SPARSE_VECTOR_NAME: object()}
            sparse = {SPARSE_VECTOR_NAME: object()}
        else:
            # Unnamed / Default dense only — wrong schema.
            vectors = object()
            sparse = None
        params = SimpleNamespace(vectors=vectors, sparse_vectors=sparse)
        config = SimpleNamespace(params=params)
        return SimpleNamespace(config=config)

    def create_collection(self, **kwargs: Any) -> None:
        self.created.append(kwargs)
        self._names.append(kwargs["collection_name"])
        self._hybrid = True

    def delete_collection(self, *, collection_name: str) -> None:
        self.deleted.append(collection_name)
        self._names = [n for n in self._names if n != collection_name]
        self._hybrid = False

    def query_points(self, **kwargs: Any) -> Any:
        self.queries.append(kwargs)
        return SimpleNamespace(
            points=[
                SimpleNamespace(
                    id="43cf51e2-8777-4f52-bc74-c2cbde0c8b04",
                    score=0.9,
                    payload={
                        "document_id": "d1",
                        "chunk_id": "c1",
                        "text": "hello",
                        "source": "qdrant",
                    },
                )
            ]
        )

    def upsert(self, **kwargs: Any) -> None:
        self.upserts.append(kwargs)

    def search(self, **kwargs: Any) -> Any:
        raise AssertionError("deprecated search must not be called")


@pytest.mark.asyncio
async def test_ensure_hybrid_collection_and_query_points(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = QdrantVectorStore(
        url="http://127.0.0.1:6333",
        api_key=None,
        collection="corp_regs",
        vector_size=1024,
    )
    fake = _FakeClient()
    monkeypatch.setattr(store, "_get_client", lambda: fake)

    hits = await store.search(
        "q",
        limit=3,
        dense_vector=[0.1] * 1024,
        sparse_vector={"hello": 1.0},
    )
    assert fake.created and fake.created[0]["collection_name"] == "corp_regs"
    cfg = fake.created[0]["vectors_config"]
    assert DENSE_VECTOR_NAME in cfg
    assert SPARSE_VECTOR_NAME in fake.created[0]["sparse_vectors_config"]
    assert fake.queries and "prefetch" in fake.queries[0]
    assert hits[0]["chunk_id"] == "c1"
    assert hits[0]["score"] == 0.9

    # Second call should not recreate
    fake.created.clear()
    await store.search("q2", limit=1, dense_vector=[0.2] * 1024)
    assert fake.created == []


@pytest.mark.asyncio
async def test_recreates_unnamed_default_collection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = QdrantVectorStore(
        url="http://127.0.0.1:6333",
        api_key=None,
        collection="corp_regs",
        vector_size=1024,
    )
    fake = _FakeClient()
    fake._names = ["corp_regs"]
    fake._hybrid = False
    monkeypatch.setattr(store, "_get_client", lambda: fake)

    await store.search("q", limit=1, dense_vector=[0.1] * 1024)
    assert fake.deleted == ["corp_regs"]
    assert fake.created and DENSE_VECTOR_NAME in fake.created[0]["vectors_config"]


@pytest.mark.asyncio
async def test_upsert_uses_named_dense_and_sparse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = QdrantVectorStore(
        url="http://127.0.0.1:6333",
        api_key=None,
        collection="corp_regs",
        vector_size=1024,
    )
    fake = _FakeClient()
    fake._names = ["corp_regs"]
    fake._hybrid = True
    monkeypatch.setattr(store, "_get_client", lambda: fake)

    await store.upsert(
        [
            {
                "document_id": "d1",
                "chunk_id": "not-a-uuid",
                "text": "t",
                "dense_vector": [0.0] * 1024,
                "sparse_vector": {"отчетность": 1.0},
            }
        ]
    )
    assert fake.upserts
    point = fake.upserts[0]["points"][0]
    import uuid

    uuid.UUID(str(point.id))
    assert isinstance(point.vector, dict)
    assert DENSE_VECTOR_NAME in point.vector
    assert SPARSE_VECTOR_NAME in point.vector
