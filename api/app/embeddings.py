"""Query embedding helper shared by Chroma retrieval and semantic caching."""

from __future__ import annotations

import httpx

from .config import Settings


def embed_text(text: str, settings: Settings) -> list[float]:
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
