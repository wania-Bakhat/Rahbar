"""Query embedding helper shared by Chroma retrieval and semantic caching."""

from __future__ import annotations

import hashlib
import math
import re

import httpx

from .config import Settings

_HASH_TEST_MODEL = "hash-test-v1"
_TOKEN = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def hash_test_embedding(text: str, dimension: int = 384) -> list[float]:
    """Stable lexical vector used only by offline fixture evaluation (never production)."""
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


def embed_text(text: str, settings: Settings) -> list[float]:
    if settings.embed_model == _HASH_TEST_MODEL:
        return hash_test_embedding(text)
    endpoint = f"{settings.ollama_url.rstrip('/')}/api/embed"
    try:
        response = httpx.post(
            endpoint,
            json={"model": settings.embed_model, "input": [text]},
            timeout=httpx.Timeout(120.0, connect=15.0),
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise RuntimeError(f"could not embed query with {settings.embed_model!r}: {exc}") from exc
    embeddings = payload.get("embeddings")
    if not isinstance(embeddings, list) or len(embeddings) != 1:
        raise RuntimeError("Ollama /api/embed returned an unexpected embeddings array")
    vector = embeddings[0]
    if not isinstance(vector, list) or not vector:
        raise RuntimeError("Ollama returned an empty query embedding")
    try:
        return [float(value) for value in vector]
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Ollama returned a non-numeric query embedding") from exc
