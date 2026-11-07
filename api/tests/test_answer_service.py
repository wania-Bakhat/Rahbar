from __future__ import annotations

from typing import Any

from app.config import Settings
from app.schemas import Answer, Citation, Passage
from app.services.answer import answer_question


class FakeRetriever:
    name = "fake"

    def __init__(self, passages: list[Passage]) -> None:
        self.passages = passages

    def retrieve(
        self, question: str, k: int, query_embedding: list[float] | None = None
    ) -> list[Passage]:
        return self.passages[:k]


class FakeProvider:
    name = "fake"

    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.calls = 0

    def generate(self, question: str, passages: list[Passage]) -> Answer:
        response = self.responses[self.calls]
        self.calls += 1
        if isinstance(response, Exception):
            raise response
        return response


class FakeCache:
    def __init__(self) -> None:
        self.embedding_calls = 0
        self.lookup_calls = 0
        self.store_calls = 0

    def embed_question(self, question: str) -> list[float]:
        self.embedding_calls += 1
        return [1.0, 0.0]

    def lookup(self, embedding: list[float]):
        self.lookup_calls += 1
        return None

    def store(self, question: str, embedding: list[float], response: Any) -> None:
        self.store_calls += 1


def _passage(score: float = 0.8) -> Passage:
    return Passage(chunk_id="c1", text="Attendance is required.", source="rules.pdf",
                   section="1 Attendance", page=2, score=score)


def _answer() -> Answer:
    return Answer(
        reasoning="The retrieved passage states the rule.",
        answer="Attendance is required. [rules.pdf / 1 Attendance]",
        citations=[Citation(source="rules.pdf", section="1 Attendance", page=2)],
        answered_from_context=True,
        confidence="high",
    )


def test_abstains_without_calling_provider_when_nothing_clears_floor() -> None:
    provider = FakeProvider([])
    settings = Settings(relevance_floor=0.25)

    result = answer_question("Question?", FakeRetriever([_passage(0.24)]), provider, settings)

    assert result.answered_from_context is False
    assert result.citations == []
    assert result.retrieved == []
    assert provider.calls == 0


def test_retries_once_after_invalid_answer_then_returns_valid_result() -> None:
    provider = FakeProvider([{"invalid": True}, _answer()])

    result = answer_question("Question?", FakeRetriever([_passage()]), provider, Settings())

    assert result.answered_from_context is True
    assert result.citations[0].source == "rules.pdf"
    assert provider.calls == 2


def test_returns_safe_fallback_after_two_invalid_answers() -> None:
    provider = FakeProvider([ValueError("bad JSON"), {"invalid": True}])

    result = answer_question("Question?", FakeRetriever([_passage()]), provider, Settings())

    assert result.answered_from_context is False
    assert result.citations == []
    assert result.confidence == "low"
    assert provider.calls == 2
    assert "couldn't produce a grounded answer" in result.answer


def test_retries_when_model_cites_a_passage_not_retrieved() -> None:
    invalid = _answer().model_copy(update={
        "citations": [Citation(source="other.pdf", section="Other", page=9)]
    })
    provider = FakeProvider([invalid, _answer()])

    result = answer_question("Question?", FakeRetriever([_passage()]), provider, Settings())

    assert result.answered_from_context is True
    assert provider.calls == 2


def test_removes_unretrieved_citations_and_keeps_matching_citations() -> None:
    answer = _answer().model_copy(update={
        "citations": [
            Citation(source="rules.pdf", section="1 Attendance", page=2),
            Citation(source="other.pdf", section="Other", page=9),
        ]
    })
    provider = FakeProvider([answer])

    result = answer_question("Question?", FakeRetriever([_passage()]), provider, Settings())

    assert result.answered_from_context is True
    assert result.citations == [Citation(source="rules.pdf", section="1 Attendance", page=2)]
    assert provider.calls == 1


def test_follow_up_question_skips_cache_lookup_and_storage() -> None:
    cache = FakeCache()

    result = answer_question("What about that?", FakeRetriever([_passage()]),
                             FakeProvider([_answer()]), Settings(), cache=cache)  # type: ignore[arg-type]

    assert result.answered_from_context is True
    assert (cache.embedding_calls, cache.lookup_calls, cache.store_calls) == (0, 0, 0)


def test_abstentions_are_never_stored_in_semantic_cache() -> None:
    cache = FakeCache()
    result = answer_question("What is unrelated?", FakeRetriever([_passage(0.1)]),
                             FakeProvider([]), Settings(), cache=cache)  # type: ignore[arg-type]

    assert result.answered_from_context is False
    assert cache.store_calls == 0


def test_failed_validations_are_never_stored_in_semantic_cache() -> None:
    cache = FakeCache()
    result = answer_question("What is the rule?", FakeRetriever([_passage()]),
                             FakeProvider([{"bad": 1}, {"bad": 2}]), Settings(),
                             cache=cache)  # type: ignore[arg-type]

    assert result.answered_from_context is False
    assert cache.store_calls == 0
