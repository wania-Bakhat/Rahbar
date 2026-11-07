from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import Response

from app.config import Settings
from app.routes.health import healthz, readyz


class FakeCollection:
    def __init__(self, *, count: int = 1, model: str = "nomic-embed-text") -> None:
        self._count = count
        self.metadata = {"embed_model": model}

    def count(self) -> int:
        return self._count


class FakeChroma:
    def __init__(self, collection: FakeCollection | None = None,
                 error: Exception | None = None) -> None:
        self.collection = collection
        self.error = error

    def get_collection(self, *, name: str) -> FakeCollection:
        if self.error:
            raise self.error
        if self.collection is None:
            raise ValueError("collection missing")
        return self.collection


class FakeRedis:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.pinged = False

    def ping(self) -> bool:
        self.pinged = True
        if self.error:
            raise self.error
        return True


def _request(chroma: FakeChroma, redis: FakeRedis) -> SimpleNamespace:
    state = SimpleNamespace(
        settings=Settings(retriever="chroma", embed_model="nomic-embed-text",
                          collection="rahbar"),
        retriever=SimpleNamespace(client=chroma),
        cache=SimpleNamespace(redis=redis),
    )
    return SimpleNamespace(app=SimpleNamespace(state=state))


def test_healthz_is_alive_without_dependency_access() -> None:
    assert healthz() == {"status": "alive"}


def test_readyz_is_ready_when_chroma_index_pin_and_redis_are_valid() -> None:
    response = Response()
    redis = FakeRedis()
    result = readyz(_request(FakeChroma(FakeCollection()), redis), response)  # type: ignore[arg-type]

    assert response.status_code == 200
    assert result["status"] == "ready"
    assert result["failures"] == []
    assert redis.pinged


@pytest.mark.parametrize(
    ("collection", "chroma_error", "redis_error", "expected_failure"),
    [
        (FakeCollection(count=0), None, None, "empty"),
        (FakeCollection(model="different-model"), None, None, "embedding model mismatch"),
        (None, RuntimeError("offline"), None, "Chroma unavailable"),
        (FakeCollection(), None, RuntimeError("offline"), "Redis unreachable"),
    ],
)
def test_readyz_returns_503_and_names_each_failed_dependency(
    collection: FakeCollection | None,
    chroma_error: Exception | None,
    redis_error: Exception | None,
    expected_failure: str,
) -> None:
    response = Response()
    result = readyz(
        _request(FakeChroma(collection, chroma_error), FakeRedis(redis_error)), response
    )  # type: ignore[arg-type]

    assert response.status_code == 503
    assert result["status"] == "not_ready"
    assert any(expected_failure in failure for failure in result["failures"])
