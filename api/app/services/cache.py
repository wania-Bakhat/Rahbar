"""Redis-backed semantic answer cache."""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, cast

from ..config import Settings
from ..embeddings import embed_text
from ..logjson import request_id_var
from ..schemas import AskResponse
from ..telemetry import CACHE_HIT_RATIO, CACHE_HITS, CACHE_LOOKUPS

_FOLLOW_UP_START = re.compile(
    r"^(?:and\b|also\b|then\b|what about\b|how about\b|what if\b|"
    r"tell me more\b|elaborate\b|does that\b|is that\b|are those\b|"
    r"what does it\b|how does it\b)",
    re.IGNORECASE,
)
_REFERENTIAL_START = re.compile(r"^(?:it|that|they|them|these|those)\b", re.IGNORECASE)


def is_follow_up(question: str) -> bool:
    """Conservatively detect short references that depend on prior-turn context."""
    normalized = question.strip()
    return bool(_FOLLOW_UP_START.search(normalized) or _REFERENTIAL_START.search(normalized))


def never_cache(question: str, answered_from_context: bool = True) -> bool:
    """Abstentions and context-dependent follow-ups must never enter or use cache."""
    return is_follow_up(question) or not answered_from_context


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


class SemanticCache:
    """Store answer records plus their query vectors under the shared cache prefix."""

    def __init__(self, settings: Settings) -> None:
        import redis

        if not 0.0 <= settings.cache_threshold <= 1.0:
            raise ValueError("CACHE_THRESHOLD must be between 0 and 1")
        if settings.cache_ttl_seconds < 1:
            raise ValueError("CACHE_TTL_SECONDS must be positive")
        if not settings.redis_cache_prefix:
            raise ValueError("REDIS_CACHE_PREFIX must not be empty")
        self.settings = settings
        self._generation: str | None = None
        self._active_prefix = settings.redis_cache_prefix
        self.redis = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            password=settings.redis_password or None,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=5,
        )

    def embed_question(self, question: str) -> list[float]:
        return embed_text(question, self.settings)

    def invalidate_for_generation(self, generation: str) -> None:
        """Invalidate stale answers by switching namespaces after an index replacement.

        Redis stays reachable only from API pods. Old-generation keys become unreachable
        immediately and expire by TTL; the indexer publishes the generation in Chroma.
        """
        if not generation or generation == self._generation:
            return
        self._generation = generation
        self._active_prefix = f"{self.settings.redis_cache_prefix}{generation}:"

    def lookup(self, embedding: list[float]) -> AskResponse | None:
        CACHE_LOOKUPS.inc()
        best_similarity = self.settings.cache_threshold
        best_response: dict[str, Any] | None = None
        for key in self.redis.scan_iter(match=f"{self._active_prefix}*", count=500):
            raw = cast(str | None, self.redis.get(key))
            if not raw:
                continue
            try:
                entry = json.loads(raw)
                cached_vector = [float(value) for value in entry["embedding"]]
                response = entry["response"]
                similarity = cosine_similarity(embedding, cached_vector)
                if similarity >= best_similarity and isinstance(response, dict):
                    best_similarity = similarity
                    best_response = response
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                # Ignore corrupt or old-format entries and continue serving requests.
                continue
        if best_response is None:
            _update_cache_hit_ratio()
            return None
        CACHE_HITS.inc()
        _update_cache_hit_ratio()
        return AskResponse.model_validate({**best_response, "request_id": request_id_var.get()})

    def store(self, question: str, embedding: list[float], response: AskResponse) -> None:
        normalized = " ".join(question.casefold().split())
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        value = {
            "question": question,
            "embedding": embedding,
            "response": response.model_dump(exclude={"request_id"}),
        }
        self.redis.setex(
            f"{self._active_prefix}{digest}",
            self.settings.cache_ttl_seconds,
            json.dumps(value, ensure_ascii=False),
        )


def _update_cache_hit_ratio() -> None:
    lookups = CACHE_LOOKUPS._value.get()
    hits = CACHE_HITS._value.get()
    CACHE_HIT_RATIO.set(hits / lookups if lookups else 0.0)
