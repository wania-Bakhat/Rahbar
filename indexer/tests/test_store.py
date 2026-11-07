from __future__ import annotations

from types import SimpleNamespace
from typing import Any

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


def test_store_recreates_collection_and_records_model_and_dimension(monkeypatch) -> None:
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
    first_collection = client.collections["rahbar"]
    assert first_collection.metadata["embed_model"] == "nomic-embed-text"
    assert first_collection.metadata["dimension"] == 3
    assert first_collection.rows["chunk-1"][2] == chunk.metadata()

    assert store([chunk], [[0.1, 0.2, 0.3]], settings) == 1
    assert client.deleted == ["rahbar"]
    assert client.collections["rahbar"] is not first_collection
