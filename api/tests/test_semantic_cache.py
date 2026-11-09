from __future__ import annotations

import json
from typing import Any

from app.config import Settings
from app.schemas import AskResponse, RetrievedRef
from app.services.cache import SemanticCache, cosine_similarity, is_follow_up


class FakeRedis:
    def __init__(self, **kwargs: Any) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def scan_iter(self, *, match: str, count: int):
        prefix = match.removesuffix("*")
        return iter(key for key in self.values if key.startswith(prefix))

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def setex(self, key: str, seconds: int, value: str) -> None:
        self.values[key] = value
        self.ttls[key] = seconds


def _response() -> AskResponse:
    return AskResponse(
        request_id="original-request",
        answer="Attendance is required.",
        citations=[],
        answered_from_context=True,
        confidence="medium",
        retrieved=[RetrievedRef(chunk_id="c1", source="rules.pdf", section="1", page=1,
                                score=0.9)],
        provider="ollama",
    )


def test_cache_uses_cosine_threshold_and_refreshes_request_id(monkeypatch) -> None:
    client: FakeRedis | None = None

    def create_client(**kwargs: Any) -> FakeRedis:
        nonlocal client
        client = FakeRedis(**kwargs)
        return client

    monkeypatch.setattr("redis.Redis", create_client)
    cache = SemanticCache(Settings(cache_threshold=0.9, cache_ttl_seconds=120))
    cache.store("Attendance rule?", [1.0, 0.0], _response())

    assert client is not None
    key = next(iter(client.values))
    stored = json.loads(client.values[key])
    assert stored["embedding"] == [1.0, 0.0]
    assert client.ttls[key] == 120
    hit = cache.lookup([0.95, 0.3122498999])
    assert hit is not None
    assert hit.request_id != "original-request"
    assert cache.lookup([0.0, 1.0]) is None
    assert cosine_similarity([1.0, 0.0], [0.95, 0.3122498999]) >= 0.9


def test_follow_up_detector_catches_referential_questions() -> None:
    assert is_follow_up("What about that?")
    assert is_follow_up("It also has a fee?")
    assert not is_follow_up("What is the attendance policy?")


def test_new_index_generation_switches_cache_namespace(monkeypatch) -> None:
    client: FakeRedis | None = None

    def create_client(**kwargs: Any) -> FakeRedis:
        nonlocal client
        client = FakeRedis(**kwargs)
        return client

    monkeypatch.setattr("redis.Redis", create_client)
    cache = SemanticCache(Settings(cache_threshold=0.9))
    cache.invalidate_for_generation("generation-a")
    cache.store("Attendance rule?", [1.0, 0.0], _response())
    assert client is not None
    old_key = next(iter(client.values))
    assert old_key.startswith("rahbar:cache:generation-a:")

    cache.invalidate_for_generation("generation-b")
    assert cache.lookup([1.0, 0.0]) is None
    cache.store("Attendance rule?", [1.0, 0.0], _response())
    new_key = next(key for key in client.values if key != old_key)
    assert new_key.startswith("rahbar:cache:generation-b:")
