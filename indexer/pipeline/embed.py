"""Stage 4: Embed. One vector per chunk, from the pinned model only."""

from __future__ import annotations

import os

import httpx

from .config import IndexerSettings


def embed(texts: list[str], settings: IndexerSettings) -> list[list[float]]:
    """Embed with settings.embed_model and nothing else.

    With Ollama: POST {ollama_url}/api/embed with {"model": ..., "input": [texts]}
    returns {"embeddings": [[...], ...]}. Batch the calls; one request per chunk is slow.
    """
    if not texts:
        return []
    batch_size = int(os.environ.get("EMBED_BATCH_SIZE", "64"))
    if batch_size < 1:
        raise ValueError("EMBED_BATCH_SIZE must be a positive integer")

    endpoint = f"{settings.ollama_url.rstrip('/')}/api/embed"
    vectors: list[list[float]] = []
    with httpx.Client(timeout=httpx.Timeout(180.0, connect=15.0)) as client:
        for start in range(0, len(texts), batch_size):
            batch = texts[start:start + batch_size]
            try:
                response = client.post(endpoint, json={"model": settings.embed_model,
                                                       "input": batch})
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise RuntimeError(
                    f"embedding request failed for model {settings.embed_model!r} "
                    f"(batch starting at {start}): {exc}"
                ) from exc

            batch_vectors = payload.get("embeddings")
            if not isinstance(batch_vectors, list) or len(batch_vectors) != len(batch):
                raise RuntimeError("Ollama /api/embed returned an unexpected embeddings array")
            for vector in batch_vectors:
                if not isinstance(vector, list) or not vector:
                    raise RuntimeError("Ollama returned an empty or invalid embedding vector")
                try:
                    vectors.append([float(value) for value in vector])
                except (TypeError, ValueError) as exc:
                    raise RuntimeError("Ollama returned a non-numeric embedding value") from exc

    dimensions = {len(vector) for vector in vectors}
    if len(vectors) != len(texts) or len(dimensions) != 1:
        raise RuntimeError("embedding service returned inconsistent vector dimensions")
    return vectors
