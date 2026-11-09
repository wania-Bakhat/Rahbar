from __future__ import annotations

from typing import Any

import pytest

from app.config import Settings
from app.retrieval.chroma import ChromaRetriever
from app.schemas import Passage


class FakeCollection:
    def __init__(self) -> None:
        self.query_args: dict[str, Any] = {}
        self.metadata: dict[str, Any] = {}

    def query(self, **kwargs: Any) -> dict[str, Any]:
        self.query_args = kwargs
        return {
            "ids": [["current", "old"]],
            "documents": [["Current policy text.", "Old policy text."]],
            "metadatas": [[
                {"source": "policy.pdf", "section": "2.1 Attendance", "page": 4,
                 "doc_version": "2026", "superseded": False},
                {"source": "policy.pdf", "section": "2 Attendance", "page": 3,
                 "doc_version": "2023", "superseded": True},
            ]],
            "distances": [[0.12, 0.2]],
        }


class FakeClient:
    def __init__(self, collection: FakeCollection) -> None:
        self.collection = collection
        self.requested_collection: str | None = None

    def get_collection(self, name: str) -> FakeCollection:
        self.requested_collection = name
        return self.collection


def _retriever() -> tuple[ChromaRetriever, FakeCollection]:
    collection = FakeCollection()
    retriever = object.__new__(ChromaRetriever)
    retriever.settings = Settings(ollama_url="http://ollama:11434", collection="rahbar")
    retriever.client = FakeClient(collection)
    return retriever, collection


def test_retriever_resolves_published_collection_from_catalog() -> None:
    retriever, active = _retriever()
    catalog = FakeCollection()
    catalog.metadata = {
        "active_collection": "rahbar__generation-b",
        "index_generation": "generation-b",
    }
    requested: list[str] = []

    class CatalogClient:
        def get_collection(self, *, name: str) -> FakeCollection:
            requested.append(name)
            return catalog if name == "rahbar_catalog" else active

    retriever.client = CatalogClient()

    assert retriever.active_collection() is active
    assert retriever.index_generation() == "generation-b"
    assert requested == ["rahbar_catalog", "rahbar__generation-b", "rahbar_catalog"]


def test_retrieve_embeds_with_pinned_model_and_maps_current_passages(monkeypatch) -> None:
    retriever, collection = _retriever()
    calls: list[tuple[str, dict[str, Any]]] = []

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return {"embeddings": [[0.1, 0.2, 0.3]]}

    def fake_post(url: str, *, json: dict[str, Any], timeout: Any) -> Response:
        calls.append((url, json))
        return Response()

    monkeypatch.setattr("app.embeddings.httpx.post", fake_post)
    passages = retriever.retrieve("attendance rule?", 5)

    assert calls == [
        ("http://ollama:11434/api/embed",
         {"model": "nomic-embed-text", "input": ["attendance rule?"]})
    ]
    assert collection.query_args["query_embeddings"] == [[0.1, 0.2, 0.3]]
    assert collection.query_args["where"] == {"superseded": False}
    assert passages == [Passage(
        chunk_id="current", text="Current policy text.", source="policy.pdf",
        section="2.1 Attendance", page=4, score=0.88,
    )]


def test_non_positive_k_returns_without_external_calls(monkeypatch) -> None:
    retriever, _ = _retriever()

    def fail(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("should not embed or query when k is non-positive")

    monkeypatch.setattr("app.retrieval.chroma.embed_text", fail)
    assert retriever.retrieve("question", 0) == []


def test_historical_question_can_retrieve_superseded_versions(monkeypatch) -> None:
    retriever, collection = _retriever()

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return {"embeddings": [[0.1, 0.2, 0.3]]}

    monkeypatch.setattr("app.embeddings.httpx.post", lambda *args, **kwargs: Response())
    passages = retriever.retrieve("What did the 2023 policy say?", 5)

    assert "where" not in collection.query_args
    assert [passage.chunk_id for passage in passages] == ["current", "old"]


def test_explicitly_named_superseded_source_is_filtered_by_filename(monkeypatch) -> None:
    retriever, collection = _retriever()

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return {"embeddings": [[0.1, 0.2, 0.3]]}

    monkeypatch.setattr("app.embeddings.httpx.post", lambda *args, **kwargs: Response())
    retriever.retrieve(
        "In the superseded short 2026 Prospectus Academic Rules, what numbered rule is labelled Attendance Requirement?",
        5,
    )

    assert collection.query_args["where"] == {
        "source": "prospectus-academic-rules-2026.pdf"
    }


def test_explicitly_named_student_handbook_is_filtered_by_filename(monkeypatch) -> None:
    retriever, collection = _retriever()

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return {"embeddings": [[0.1, 0.2, 0.3]]}

    monkeypatch.setattr("app.embeddings.httpx.post", lambda *args, **kwargs: Response())
    retriever.retrieve(
        "According to the 2026 Student Handbook, what guidance is given about generative AI?",
        5,
    )

    assert collection.query_args["where"] == {
        "source": "student-handbook-2026.pdf"
    }


def test_distinctive_student_handbook_heading_uses_exact_section_filter(monkeypatch) -> None:
    retriever, collection = _retriever()

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return {"embeddings": [[0.1, 0.2, 0.3]]}

    monkeypatch.setattr("app.embeddings.httpx.post", lambda *args, **kwargs: Response())
    retriever.retrieve("What training and support does the Student Handbook describe?", 5)

    assert collection.query_args["where"] == {"$and": [
        {"source": "student-handbook-2026.pdf"},
        {"section": "10. Training and Support"},
    ]}


@pytest.mark.parametrize(
    ("question", "source"),
    [
        ("May a student repeat a course under current academic rules?",
         "academic-rules-handbook-2026.pdf"),
        ("What training does the Student Handbook describe?",
         "student-handbook-2026.pdf"),
        ("What is reported in the 2023-24 annual report?",
         "annual-report-2023-24.pdf"),
    ],
)
def test_explicit_document_scope_filters_source_filename(
    monkeypatch, question: str, source: str,
) -> None:
    retriever, collection = _retriever()

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return {"embeddings": [[0.1, 0.2, 0.3]]}

    monkeypatch.setattr("app.embeddings.httpx.post", lambda *args, **kwargs: Response())
    retriever.retrieve(question, 5)

    assert collection.query_args["where"] == {"source": source}


def test_retrieve_drops_passages_below_relevance_floor(monkeypatch) -> None:
    retriever, collection = _retriever()
    original_query = collection.query

    def low_relevance_query(**kwargs: Any) -> dict[str, Any]:
        result = original_query(**kwargs)
        result["distances"] = [[0.9, 0.95]]
        return result

    collection.query = low_relevance_query  # type: ignore[method-assign]

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return {"embeddings": [[0.1, 0.2, 0.3]]}

    monkeypatch.setattr("app.embeddings.httpx.post", lambda *args, **kwargs: Response())
    assert retriever.retrieve("attendance requirement?", 5) == []
