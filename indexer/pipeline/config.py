"""Indexer configuration, from the same ConfigMap the API reads (section 4.1)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

FailureMode = Literal[
    "off", "no_ocr", "chunks_100", "top_k_1", "no_context_instruction",
    "no_superseded_filter", "temperature_1_2",
]
FAILURE_MODES = (
    "off", "no_ocr", "chunks_100", "top_k_1", "no_context_instruction",
    "no_superseded_filter", "temperature_1_2",
)


@dataclass(frozen=True)
class IndexerSettings:
    embed_model: str        # EMBED_MODEL: must equal the API's value (section 4.4)
    chroma_host: str
    chroma_port: int
    collection: str
    corpus_dir: str         # where the documents and _index.json sit inside the Job's pod
    chunk_size: int
    chunk_overlap: int
    ollama_url: str
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""
    redis_cache_prefix: str = "rahbar:cache:"
    failure_mode: FailureMode = "off"


def get_settings() -> IndexerSettings:
    failure_mode = os.environ.get("FAILURE_MODE", "off")
    if failure_mode not in FAILURE_MODES:
        raise ValueError(
            f"invalid indexer FAILURE_MODE {failure_mode!r}; choose exactly one of: "
            + ", ".join(FAILURE_MODES)
        )
    return IndexerSettings(
        embed_model=os.environ.get("EMBED_MODEL", "nomic-embed-text"),
        chroma_host=os.environ.get("CHROMA_HOST", "chroma"),
        chroma_port=int(os.environ.get("CHROMA_PORT", 8000)),
        collection=os.environ.get("CHROMA_COLLECTION", "rahbar"),
        corpus_dir=os.environ.get("CORPUS_DIR", "/corpus"),
        chunk_size=int(os.environ.get("CHUNK_SIZE", 400)),
        chunk_overlap=int(os.environ.get("CHUNK_OVERLAP", 50)),
        ollama_url=os.environ.get("OLLAMA_URL", "http://host.minikube.internal:11434"),
        redis_host=os.environ.get("REDIS_HOST", "redis"),
        redis_port=int(os.environ.get("REDIS_PORT", 6379)),
        redis_db=int(os.environ.get("REDIS_DB", 0)),
        redis_password=os.environ.get("REDIS_PASSWORD", ""),
        redis_cache_prefix=os.environ.get("REDIS_CACHE_PREFIX", "rahbar:cache:"),
        failure_mode=failure_mode,  # type: ignore[arg-type]
    )
