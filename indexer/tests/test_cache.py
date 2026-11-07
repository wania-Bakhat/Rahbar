from __future__ import annotations

from typing import Any

from pipeline.cache import flush_cache
from pipeline.config import get_settings


class FakeRedis:
    def __init__(self, **kwargs: Any) -> None:
        self.options = kwargs
        self.deleted: list[str] = []
        self.pattern: str | None = None
        self.pinged = False

    def ping(self) -> bool:
        self.pinged = True
        return True

    def scan_iter(self, *, match: str, count: int):
        self.pattern = match
        assert count == 500
        return iter(["rahbar:cache:a", "rahbar:cache:b"])

    def delete(self, *keys: str) -> int:
        self.deleted.extend(keys)
        return len(keys)


def test_flush_cache_removes_only_keys_under_configured_prefix(monkeypatch) -> None:
    client: FakeRedis | None = None

    def create_client(**kwargs: Any) -> FakeRedis:
        nonlocal client
        client = FakeRedis(**kwargs)
        return client

    monkeypatch.setattr("redis.Redis", create_client)
    settings = get_settings()

    assert flush_cache(settings) == 2
    assert client is not None
    assert client.pinged
    assert client.pattern == "rahbar:cache:*"
    assert client.deleted == ["rahbar:cache:a", "rahbar:cache:b"]
