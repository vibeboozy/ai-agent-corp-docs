"""
ANCHOR: tests.adapters.test_qdrant_adapter
PURPOSE: Unit tests for Qdrant ensure-collection, query_points, UUID point ids.
Dependencies: app.adapters.vectorstore.qdrant (mocked client)
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.adapters.vectorstore.qdrant import QdrantVectorStore, _point_id


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


class _FakeCollections:
    def __init__(self, names: list[str]) -> None:
        self.collections = [SimpleNamespace(name=n) for n in names]


class _FakeClient:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.queries: list[dict[str, Any]] = []
        self.upserts: list[dict[str, Any]] = []
        self._names: list[str] = []

    def get_collections(self) -> _FakeCollections:
        return _FakeCollections(self._names)

    def create_collection(self, **kwargs: Any) -> None:
        self.created.append(kwargs)
        self._names.append(kwargs["collection_name"])

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
async def test_ensure_collection_and_query_points(monkeypatch: pytest.MonkeyPatch) -> None:
    store = QdrantVectorStore(
        url="http://127.0.0.1:6333",
        api_key=None,
        collection="corp_regs",
        vector_size=1024,
    )
    fake = _FakeClient()
    monkeypatch.setattr(store, "_get_client", lambda: fake)

    hits = await store.search("q", limit=3, dense_vector=[0.1] * 1024)
    assert fake.created and fake.created[0]["collection_name"] == "corp_regs"
    assert fake.queries and "query" in fake.queries[0]
    assert hits[0]["chunk_id"] == "c1"
    assert hits[0]["score"] == 0.9

    # Second call should not recreate
    fake.created.clear()
    await store.search("q2", limit=1, dense_vector=[0.2] * 1024)
    assert fake.created == []


@pytest.mark.asyncio
async def test_upsert_uses_uuid_point_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    store = QdrantVectorStore(
        url="http://127.0.0.1:6333",
        api_key=None,
        collection="corp_regs",
        vector_size=1024,
    )
    fake = _FakeClient()
    fake._names = ["corp_regs"]
    monkeypatch.setattr(store, "_get_client", lambda: fake)

    await store.upsert(
        [
            {
                "document_id": "d1",
                "chunk_id": "not-a-uuid",
                "text": "t",
                "dense_vector": [0.0] * 1024,
            }
        ]
    )
    assert fake.upserts
    point = fake.upserts[0]["points"][0]
    import uuid

    uuid.UUID(str(point.id))
