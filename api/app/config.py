"""Runtime configuration, read once from environment variables.

On the cluster these variables come from your ConfigMap and Secret (section 4.1).
Nothing here is baked into the image, so one image runs in every environment.
Add your own keys (relevance floor, cache settings, ...) the same way.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

FailureMode = Literal[
    "off", "no_ocr", "chunks_100", "top_k_1", "no_context_instruction",
    "no_superseded_filter", "temperature_1_2",
]
FAILURE_MODES: tuple[str, ...] = (
    "off", "no_ocr", "chunks_100", "top_k_1", "no_context_instruction",
    "no_superseded_filter", "temperature_1_2",
)


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


@dataclass(frozen=True)
class Settings:
    # Which implementations to load. "stub" needs no cluster, no model, no network.
    retriever: str = "stub"          # RETRIEVER: stub | chroma
    llm_provider: str = "stub"       # LLM_PROVIDER: stub | ollama-host | ollama-incluster | hosted

    # The embedding pin (section 4.4). The indexer reads the same ConfigMap key.
    embed_model: str = "nomic-embed-text"

    # Vector store
    chroma_host: str = "chroma"
    chroma_port: int = 8000
    collection: str = "rahbar"

    # Retrieval and generation
    top_k: int = 5
    relevance_floor: float = 0.25
    failure_mode: FailureMode = "off"
    cache_threshold: float = 0.95
    cache_ttl_seconds: int = 86400
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = field(default="", repr=False)
    redis_cache_prefix: str = "rahbar:cache:"
    temperature: float = 0.2
    llm_model: str = "llama3.2:3b"
    ollama_url: str = "http://host.minikube.internal:11434"
    hosted_base_url: str = ""        # e.g. an OpenAI-compatible endpoint
    llm_api_key: str = field(default="", repr=False)   # from the Secret; never log it

    log_level: str = "INFO"


def get_settings() -> Settings:
    failure_mode = os.environ.get("FAILURE_MODE", "off")
    if failure_mode not in FAILURE_MODES:
        raise ValueError(
            f"invalid FAILURE_MODE {failure_mode!r}; choose exactly one of: "
            + ", ".join(FAILURE_MODES)
        )
    return Settings(
        retriever=os.environ.get("RETRIEVER", "stub"),
        llm_provider=os.environ.get("LLM_PROVIDER", "stub"),
        embed_model=os.environ.get("EMBED_MODEL", "nomic-embed-text"),
        chroma_host=os.environ.get("CHROMA_HOST", "chroma"),
        chroma_port=_int("CHROMA_PORT", 8000),
        collection=os.environ.get("CHROMA_COLLECTION", "rahbar"),
        top_k=_int("TOP_K", 5),
        relevance_floor=_float("RELEVANCE_FLOOR", 0.25),
        failure_mode=failure_mode,  # type: ignore[arg-type]
        cache_threshold=_float("CACHE_THRESHOLD", 0.95),
        cache_ttl_seconds=_int("CACHE_TTL_SECONDS", 86400),
        redis_host=os.environ.get("REDIS_HOST", "redis"),
        redis_port=_int("REDIS_PORT", 6379),
        redis_db=_int("REDIS_DB", 0),
        redis_password=os.environ.get("REDIS_PASSWORD", ""),
        redis_cache_prefix=os.environ.get("REDIS_CACHE_PREFIX", "rahbar:cache:"),
        temperature=_float("TEMPERATURE", 0.2),
        llm_model=os.environ.get("LLM_MODEL", "llama3.2:3b"),
        ollama_url=os.environ.get("OLLAMA_URL", "http://host.minikube.internal:11434"),
        hosted_base_url=os.environ.get("HOSTED_BASE_URL", ""),
        llm_api_key=os.environ.get("LLM_API_KEY", ""),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )
