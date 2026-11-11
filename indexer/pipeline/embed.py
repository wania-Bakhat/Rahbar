"""Stage 4: Embed. One vector per chunk, from the pinned model only."""

from __future__ import annotations

import hashlib
import math
import os
import re

import httpx

from .config import IndexerSettings

_HASH_TEST_MODEL = "hash-test-v1"
_TOKEN = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def _hash_test_embedding(text: str, dimension: int = 384) -> list[float]:
    tokens = [token.casefold() for token in _TOKEN.findall(text)]
    features = tokens + [f"{left}_{right}" for left, right in zip(tokens, tokens[1:])]
    vector = [0.0] * dimension
    for feature in features:
        digest = hashlib.sha256(feature.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimension
        vector[index] += 1.0 if digest[4] & 1 else -1.0
    norm = math.sqrt(sum(value * value for value in vector))
    if norm:
        vector = [value / norm for value in vector]
    return vector


def embed(texts: list[str], settings: IndexerSettings) -> list[list[float]]:
    """Embed with settings.embed_model and nothing else.

    With Ollama: POST {ollama_url}/api/embed with {"model": ..., "input": [texts]}
    returns {"embeddings": [[...], ...]}. Batch the calls; one request per chunk is slow.
    """
    if not texts:
        return []
    if settings.embed_model == _HASH_TEST_MODEL:
        return [_hash_test_embedding(text) for text in texts]
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
