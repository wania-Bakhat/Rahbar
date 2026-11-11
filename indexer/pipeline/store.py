"""Stage 5: Store. The only code in the whole system that writes to Chroma."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .config import IndexerSettings
from .models import Chunk


def get_client(settings: IndexerSettings) -> Any:
    import chromadb  # the thin client, from chromadb-client in requirements.txt
    from chromadb.config import Settings as ChromaSettings

    return chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port,
                               settings=ChromaSettings(anonymized_telemetry=False))


def store(chunks: list[Chunk], vectors: list[list[float]], settings: IndexerSettings) -> int:
    """Build a versioned collection and publish it only after all chunks are stored.

    The catalog pointer is the publication step: API readers continue using the old
    collection while this job builds the replacement. Keep the active and immediately
    previous collection so in-flight API requests and rollback remain safe.
    """
    if len(chunks) != len(vectors):
        raise ValueError(f"received {len(chunks)} chunks but {len(vectors)} vectors")
    if not chunks:
        raise ValueError("refusing to publish an empty index; keeping the active generation")
    if any(not vector for vector in vectors):
        raise ValueError("embedding vectors cannot be empty")
    dimensions = {len(vector) for vector in vectors}
    if len(dimensions) != 1:
        raise ValueError("all embedding vectors must have the same dimension")
    dimension = dimensions.pop()

    generation = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}".lower()
    client = get_client(settings)
    collection_name = f"{settings.collection}__{generation}"
    metadata = {
        "hnsw:space": "cosine",
        "embed_model": settings.embed_model,
        "dimension": dimension,
        "index_generation": generation,
    }
    collection = client.create_collection(name=collection_name, metadata=metadata)

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

    if int(collection.count()) != len(chunks):
        raise RuntimeError(
            f"staged collection {collection_name} has {collection.count()} records; "
            f"expected {len(chunks)}"
        )

    catalog_name = f"{settings.collection}_catalog"
    catalog = client.get_or_create_collection(name=catalog_name)
    old_metadata = catalog.metadata or {}
    old_active = old_metadata.get("active_collection")
    collection_names = {
        item.name if hasattr(item, "name") else str(item)
        for item in client.list_collections()
    }
    if not old_active and settings.collection in collection_names:
        old_active = settings.collection  # adopt an existing single-collection index

    # One metadata update switches new API reads to the complete staged index.
    catalog.modify(metadata={
        "active_collection": collection_name,
        "previous_collection": str(old_active or ""),
        "index_generation": generation,
        "embed_model": settings.embed_model,
        "dimension": dimension,
    })

    # Keep the active and previous generations. Remove only older staged generations,
    # which are no longer addressable and cannot be used by new API requests.
    keep = {collection_name, str(old_active or ""), catalog_name}
    for name in collection_names:
        if name.startswith(f"{settings.collection}__") and name not in keep:
            client.delete_collection(name)
    return len(chunks)
