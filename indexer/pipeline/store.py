"""Stage 5: Store. The only code in the whole system that writes to Chroma."""

from __future__ import annotations

from typing import Any

from .config import IndexerSettings
from .models import Chunk


def get_client(settings: IndexerSettings) -> Any:
    import chromadb  # the thin client, from chromadb-client in requirements.txt
    from chromadb.config import Settings as ChromaSettings

    return chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port,
                               settings=ChromaSettings(anonymized_telemetry=False))


def store(chunks: list[Chunk], vectors: list[list[float]], settings: IndexerSettings) -> int:
    """Write every chunk with its vector and metadata, and record the embedding model
    and vector dimension in the collection metadata (section 4.4). Return the count."""
    if len(chunks) != len(vectors):
        raise ValueError(f"received {len(chunks)} chunks but {len(vectors)} vectors")
    if not chunks:
        return 0
    if any(not vector for vector in vectors):
        raise ValueError("embedding vectors cannot be empty")
    dimensions = {len(vector) for vector in vectors}
    if len(dimensions) != 1:
        raise ValueError("all embedding vectors must have the same dimension")
    dimension = dimensions.pop()

    client = get_client(settings)
    metadata = {"hnsw:space": "cosine", "embed_model": settings.embed_model,
                "dimension": dimension}
    # Every run builds a clean index, so removed documents and old chunks cannot
    # linger after corpus changes. The API can briefly see an empty collection.
    existing_names = {collection.name for collection in client.list_collections()}
    if settings.collection in existing_names:
        client.delete_collection(settings.collection)
    collection = client.create_collection(name=settings.collection, metadata=metadata)

    batch_size = 500
    for start in range(0, len(chunks), batch_size):
        batch_chunks = chunks[start:start + batch_size]
        batch_vectors = vectors[start:start + batch_size]
        collection.upsert(
            ids=[chunk.id for chunk in batch_chunks],
            documents=[chunk.text for chunk in batch_chunks],
            embeddings=batch_vectors,
            metadatas=[chunk.metadata() for chunk in batch_chunks],
        )
    return len(chunks)
