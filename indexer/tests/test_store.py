from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from pipeline.config import IndexerSettings
from pipeline.models import Chunk
from pipeline.store import store


class FakeCollection:
    def __init__(self, name: str, metadata: dict[str, Any]) -> None:
        self.name = name
        self.metadata = metadata
        self.rows: dict[str, tuple[str, list[float], dict[str, Any]]] = {}

    def upsert(self, *, ids, documents, embeddings, metadatas) -> None:
        for chunk_id, document, embedding, metadata in zip(ids, documents, embeddings, metadatas):
            self.rows[chunk_id] = (document, embedding, metadata)

    def count(self) -> int:
        return len(self.rows)

    def modify(self, *, metadata: dict[str, Any]) -> None:
        self.metadata = metadata


class FakeClient:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}
        self.deleted: list[str] = []

    def list_collections(self) -> list[SimpleNamespace]:
        return [SimpleNamespace(name=name) for name in self.collections]

    def delete_collection(self, name: str) -> None:
        self.deleted.append(name)
        del self.collections[name]

    def create_collection(self, *, name: str, metadata: dict[str, Any]) -> FakeCollection:
        collection = FakeCollection(name, metadata)
        self.collections[name] = collection
        return collection

    def get_or_create_collection(self, *, name: str) -> FakeCollection:
        return self.collections.setdefault(name, FakeCollection(name, {}))


def test_store_publishes_complete_generation_and_retains_previous(monkeypatch) -> None:
    client = FakeClient()
    settings = IndexerSettings(
        embed_model="nomic-embed-text", chroma_host="chroma", chroma_port=8000,
        collection="rahbar", corpus_dir="/corpus", chunk_size=400,
        chunk_overlap=50, ollama_url="http://ollama:11434",
    )
    chunk = Chunk(
        id="chunk-1", text="Attendance policy", source="rules.pdf",
        section="1 Attendance", page=2, doc_version="2026", superseded=False,
    )
    monkeypatch.setattr("pipeline.store.get_client", lambda _settings: client)

    assert store([chunk], [[0.1, 0.2, 0.3]], settings) == 1
    catalog = client.collections["rahbar_catalog"]
    first_name = str(catalog.metadata["active_collection"])
    first_collection = client.collections[first_name]
    assert first_collection.metadata["embed_model"] == "nomic-embed-text"
    assert first_collection.metadata["dimension"] == 3
    assert first_collection.rows["chunk-1"][2] == chunk.metadata()
    assert catalog.metadata["index_generation"] == first_collection.metadata["index_generation"]

    assert store([chunk], [[0.1, 0.2, 0.3]], settings) == 1
    second_name = str(catalog.metadata["active_collection"])
    assert second_name != first_name
    assert catalog.metadata["previous_collection"] == first_name
    assert first_name in client.collections
    assert second_name in client.collections

    assert store([chunk], [[0.1, 0.2, 0.3]], settings) == 1
    third_name = str(catalog.metadata["active_collection"])
    assert catalog.metadata["previous_collection"] == second_name
    assert first_name in client.deleted
    assert second_name in client.collections
    assert third_name in client.collections


def test_store_rejects_empty_index_without_creating_any_collection(monkeypatch) -> None:
    client = FakeClient()
    settings = IndexerSettings(
        embed_model="nomic-embed-text", chroma_host="chroma", chroma_port=8000,
        collection="rahbar", corpus_dir="/corpus", chunk_size=400,
        chunk_overlap=50, ollama_url="http://ollama:11434",
    )
    monkeypatch.setattr("pipeline.store.get_client", lambda _settings: client)

    with pytest.raises(ValueError, match="empty index"):
        store([], [], settings)

    assert client.collections == {}
