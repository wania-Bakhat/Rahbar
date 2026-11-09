from __future__ import annotations

from typing import Any

from app.config import Settings
from app.schemas import Answer, AskResponse, Citation, Passage, RetrievedRef
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
        self.cached_response: AskResponse | None = None
        self.generations: list[str] = []

    def invalidate_for_generation(self, generation: str) -> None:
        self.generations.append(generation)

    def embed_question(self, question: str) -> list[float]:
        self.embedding_calls += 1
        return [1.0, 0.0]

    def lookup(self, embedding: list[float]):
        self.lookup_calls += 1
        return self.cached_response

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


def test_rejects_factual_answer_marked_as_abstention() -> None:
    misleading_abstention = Answer(
        reasoning="A retrieved passage mentions attendance.",
        answer="100% [4 / 1.21]",
        citations=[],
        answered_from_context=False,
        confidence="low",
    )
    provider = FakeProvider([misleading_abstention, misleading_abstention])

    result = answer_question(
        "What attendance rule applies?", FakeRetriever([_passage()]), provider, Settings()
    )

    assert result.answered_from_context is False
    assert result.citations == []
    assert "couldn't produce a grounded answer" in result.answer
    assert provider.calls == 2


def test_repairs_short_verbatim_answer_with_retrieved_clause_citation() -> None:
    summer = Passage(
        chunk_id="summer", text="The 80% attendance rule applies to summer courses.",
        source="rules-2026.pdf", section="6.7 Summer attendance", page=28, score=0.83,
    )
    current = Passage(
        chunk_id="current", text="Clause 1.21 requires 100% attendance in regular lectures.",
        source="rules-2026.pdf", section="1.21 Attendance", page=10, score=0.76,
    )
    inconsistent = Answer(
        reasoning="Clause 1.21 states the attendance requirement.",
        answer="The regular-course threshold is 100% [4 / 1.21].",
        citations=[], answered_from_context=False, confidence="low",
    )
    provider = FakeProvider([inconsistent])

    result = answer_question(
        "For a regular semester course, not a summer course, what attendance percentage "
        "does clause 1.21 require?",
        FakeRetriever([summer, current]), provider, Settings(),
    )

    assert result.answered_from_context is True
    assert result.answer == "100% [rules-2026.pdf / 1.21 Attendance]"
    assert result.citations == [Citation(
        source="rules-2026.pdf", section="1.21 Attendance", page=10,
    )]
    assert result.confidence == "medium"
    assert provider.calls == 1


def test_repairs_missing_or_wrong_tuition_amount_from_tuition_passage() -> None:
    tuition = Passage(
        chunk_id="tuition",
        text=("Master and PhD Degree Programs Tuition fee for all Campuses and Programs "
              "is Rs. 12,000 per credit hour. Bachelor's Degree Programs Tuition fee "
              "for all Campuses and Programs is Rs. 12,000 per credit hour."),
        source="prospectus-fee-information-2026.pdf",
        section="3. Tuition Fee",
        page=1,
        score=0.81,
    )
    wrong_amount = Answer(
        reasoning="The retrieved passage covers the tuition fee.",
        answer="The fee is Rs. 300 per credit hour [prospectus-fee-information-2026.pdf / 3. Tuition Fee]",
        citations=[Citation(
            source="prospectus-fee-information-2026.pdf",
            section="3. Tuition Fee",
            page=1,
        )],
        answered_from_context=True,
        confidence="medium",
    )
    provider = FakeProvider([wrong_amount])

    result = answer_question(
        "What is the listed tuition fee per credit hour in the 2026 prospectus fee information?",
        FakeRetriever([tuition]), provider, Settings(),
    )

    assert result.answer == (
        "The listed tuition fee is Rs. 12,000 per credit hour "
        "[prospectus-fee-information-2026.pdf / 3. Tuition Fee]"
    )
    assert result.citations == [Citation(
        source="prospectus-fee-information-2026.pdf",
        section="3. Tuition Fee",
        page=1,
    )]
    assert result.answered_from_context is True
    assert provider.calls == 1


def test_repairs_numbered_rule_answer_from_explicit_historical_heading() -> None:
    historical = Passage(
        chunk_id="historical-attendance-heading",
        text="Rule 1 is labelled Attendance Requirement.",
        source="prospectus-academic-rules-2026.pdf",
        section="1. Attendance Requirement 4. Semester Course Load",
        page=1,
        score=0.82,
    )
    wrong = Answer(
        reasoning="The old prospectus mentions attendance.",
        answer="The current undergraduate attendance requirement is 80%.",
        citations=[Citation(
            source=historical.source, section=historical.section, page=historical.page,
        )],
        answered_from_context=True,
        confidence="medium",
    )
    provider = FakeProvider([wrong])

    result = answer_question(
        "In the superseded short 2026 Prospectus Academic Rules, what numbered rule is "
        "labelled Attendance Requirement?",
        FakeRetriever([historical]), provider, Settings(),
    )

    assert result.answer.startswith("Rule 1 is labelled Attendance Requirement")
    assert result.citations == [Citation(
        source=historical.source, section=historical.section, page=historical.page,
    )]
    assert result.answered_from_context is True
    assert provider.calls == 1


def test_repairs_attendance_clause_number_from_retrieved_current_heading() -> None:
    summer = Passage(
        chunk_id="summer-attendance",
        text="The 80% attendance rule applies to summer courses.",
        source="academic-rules-handbook-2026.pdf",
        section="6.7 80% attendance rule shall apply to summer courses/labs.",
        page=28,
        score=0.83,
    )
    regular = Passage(
        chunk_id="regular-attendance",
        text="Students are required to maintain 100% attendance in all lectures.",
        source="academic-rules-handbook-2026.pdf",
        section="1.21 Students are required to maintain 100% attendance in",
        page=10,
        score=0.78,
    )
    wrong = Answer(
        reasoning="Attendance rules are described in the handbook.",
        answer="The requirement appears under section 1.20 [academic-rules-handbook-2026.pdf / "
               "1.20 A student can only register for courses for which he/she has]",
        citations=[Citation(
            source="academic-rules-handbook-2026.pdf",
            section="1.20 A student can only register for courses for which he/she has",
            page=9,
        )],
        answered_from_context=True,
        confidence="medium",
    )
    provider = FakeProvider([wrong])

    result = answer_question(
        "What clause number in the current 2026 Academic Rules Handbook specifies the "
        "100% course attendance requirement?",
        FakeRetriever([summer, regular]), provider, Settings(),
    )

    assert result.answer.startswith("Clause 1.21 requires 100% attendance")
    assert result.citations == [Citation(
        source=regular.source, section=regular.section, page=regular.page,
    )]
    assert result.answered_from_context is True
    assert provider.calls == 1


def test_extracts_and_cites_relevant_sentence_after_generation_retries_fail() -> None:
    attendance = Passage(
        chunk_id="attendance-failure",
        text=("Failure to meet attendance requirements in a course will render the student "
              "ineligible to appear in the final examination of the concerned course."),
        source="academic-rules-handbook-2026.pdf",
        section="1.22 Failure to meet attendance requirements in a course will",
        page=10,
        score=0.85,
    )
    malformed = Answer(
        reasoning="The passage discusses the rule.",
        answer="The student receives an F/A grade.",
        citations=[],
        answered_from_context=False,
        confidence="low",
    )
    provider = FakeProvider([malformed])

    result = answer_question(
        "What happens when a student fails to meet a course's attendance requirement?",
        FakeRetriever([attendance]), provider, Settings(),
    )

    assert result.answered_from_context is True
    assert result.answer.startswith(attendance.text)
    assert len(result.citations) == 1
    assert result.citations[0].section == attendance.section
    assert provider.calls == 1


def test_retries_when_model_cites_a_passage_not_retrieved() -> None:
    invalid = _answer().model_copy(update={
        "citations": [Citation(source="other.pdf", section="Other", page=9)]
    })
    provider = FakeProvider([invalid, _answer()])

    result = answer_question("Question?", FakeRetriever([_passage()]), provider, Settings())

    assert result.answered_from_context is True
    assert provider.calls == 2


def test_retries_when_structured_citation_is_missing_from_answer_text() -> None:
    uncited = _answer().model_copy(update={"answer": "Attendance is required."})
    provider = FakeProvider([uncited, _answer()])

    result = answer_question("Question?", FakeRetriever([_passage()]), provider, Settings())

    assert result.answered_from_context is True
    assert result.citations[0].source == "rules.pdf"
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


def test_generation_change_during_cache_lookup_discards_stale_hit() -> None:
    class FlippingRetriever(FakeRetriever):
        generation_reads = 0

        def index_generation(self) -> str:
            self.generation_reads += 1
            return "generation-a" if self.generation_reads == 1 else "generation-b"

    cache = FakeCache()
    cache.cached_response = AskResponse(
        request_id="old-request", answer="Old generation answer.", citations=[],
        answered_from_context=True, confidence="high", provider="fake",
        retrieved=[RetrievedRef(chunk_id="old", source="rules.pdf", section="old",
                                page=1, score=0.9)],
    )
    provider = FakeProvider([_answer()])

    result = answer_question(
        "What is the current rule?", FlippingRetriever([_passage()]), provider,
        Settings(), cache=cache,  # type: ignore[arg-type]
    )

    assert result.answer == _answer().answer
    assert provider.calls == 1
    assert cache.generations == ["generation-a", "generation-b"]
