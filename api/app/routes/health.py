"""Liveness and readiness (section 4.3). They answer different questions."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from ..logjson import request_observation_var

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Is the process alive? Must never touch Chroma, Redis or the LLM."""
    return {"status": "alive"}


@router.get("/readyz")
def readyz(request: Request, response: Response) -> dict[str, object]:
    state = request.app.state
    settings = state.settings
    checks: dict[str, object] = {}
    failures: list[str] = []

    retriever = state.retriever
    chroma_client = getattr(retriever, "client", None)
    if chroma_client is None:
        checks["chroma"] = "not configured"
        failures.append("chroma not configured")
        checks["collection"] = "not checked"
        checks["embedding_model"] = "not checked"
    else:
        try:
            collection = chroma_client.get_collection(name=settings.collection)
            checks["chroma"] = "reachable"
            count = int(collection.count())
            checks["collection"] = {"name": settings.collection, "count": count}
            if count <= 0:
                failures.append(f"Chroma collection '{settings.collection}' is empty")
            metadata = collection.metadata or {}
            actual_model = metadata.get("embed_model")
            checks["embedding_model"] = {
                "expected": settings.embed_model,
                "actual": actual_model,
            }
            if actual_model != settings.embed_model:
                failures.append(
                    f"embedding model mismatch: collection has {actual_model!r}, "
                    f"API expects {settings.embed_model!r}"
                )
        except Exception as exc:
            checks["chroma"] = f"unreachable: {type(exc).__name__}"
            checks["collection"] = "not available"
            checks["embedding_model"] = "not available"
            failures.append(f"Chroma unavailable or collection '{settings.collection}' missing")

    cache = state.cache
    redis_client = getattr(cache, "redis", None)
    if redis_client is None:
        checks["redis"] = "not configured"
        failures.append("Redis not configured")
    else:
        try:
            redis_client.ping()
            checks["redis"] = "reachable"
        except Exception as exc:
            checks["redis"] = f"unreachable: {type(exc).__name__}"
            failures.append("Redis unreachable")

    if failures:
        observation = request_observation_var.get()
        if observation is not None:
            observation.update({"readiness_failures": failures, "readiness_checks": checks})
        response.status_code = 503
        return {"status": "not_ready", "checks": checks, "failures": failures}
    return {"status": "ready", "checks": checks, "failures": []}
