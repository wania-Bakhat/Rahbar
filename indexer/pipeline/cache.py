"""Helpers for invalidating cached answers after replacing the vector index."""

from __future__ import annotations

from typing import cast

from .config import IndexerSettings


def flush_cache(settings: IndexerSettings) -> int:
    """Delete RAHBAR cache keys, leaving unrelated Redis data untouched.

    Returns the number of keys removed. Redis failures propagate so the indexing
    Job does not report success while answers from the previous index may persist.
    """
    import redis

    if not settings.redis_cache_prefix:
        raise ValueError("REDIS_CACHE_PREFIX must not be empty")
    client = redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        password=settings.redis_password or None,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=10,
    )
    client.ping()
    pattern = f"{settings.redis_cache_prefix}*"
    removed = 0
    batch: list[str] = []
    for key in client.scan_iter(match=pattern, count=500):
        batch.append(key)
        if len(batch) >= 500:
            removed += cast(int, client.delete(*batch))
            batch.clear()
    if batch:
        removed += cast(int, client.delete(*batch))
    return removed
