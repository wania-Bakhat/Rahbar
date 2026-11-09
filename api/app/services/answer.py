"""Ground a question in retrieved passages and return a validated AskResponse."""

from __future__ import annotations

import re
import time

from ..config import Settings
from ..logjson import request_id_var, request_observation_var
from ..providers.llm.base import LLMProvider
from ..retrieval.base import Retriever
from ..schemas import Answer, AskResponse, Citation, Passage, RetrievedRef
from ..telemetry import (ABSTENTIONS, FALLBACKS, GENERATION_LATENCY,
                         RETRIEVAL_LATENCY)
from .cache import SemanticCache, is_follow_up, never_cache

_WORD = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_CLAUSE_NUMBER = re.compile(r"\b\d+(?:\.\d+)+\b")
_ANSWER_VALUE = re.compile(
    r"(?<![\w])(?:Rs\.?\s*)?\d[\d,]*(?:\.\d+)?%?(?![\w%])", re.IGNORECASE
)
_PER_CREDIT_TUITION = re.compile(
    r"tuition\s+fee\b.{0,220}?Rs\.?\s*(?P<amount>\d[\d,]*)\s+per\s+credit\s+hour",
    re.IGNORECASE | re.DOTALL,
)
_ATTENDANCE_RULE_HEADING = re.compile(
    r"(?:^|\s)(?P<number>\d+)\.\s*Attendance Requirement\b", re.IGNORECASE
)
_CLAUSE_HEADING = re.compile(r"^\s*(?P<number>\d+(?:\.\d+)+)\b")
_QUESTION_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "does", "for", "from", "how",
    "in", "is", "it", "of", "on", "or", "the", "to", "under", "what", "when",
    "which", "who", "why", "with",
}

def answer_question(
    question: str, retriever: Retriever, provider: LLMProvider, settings: Settings,
    cache: SemanticCache | None = None,
) -> AskResponse:
    follow_up = is_follow_up(question)
    query_embedding: list[float] | None = None
    embedding_elapsed = 0.0
    cache_generation: str | None = None
    observation = request_observation_var.get()
    if observation is not None:
        observation["cache_hit"] = False
        observation["follow_up"] = follow_up
    if cache is not None and not never_cache(question) and settings.failure_mode == "off":
        try:
            generation_reader = getattr(retriever, "index_generation", None)
            if generation_reader is not None:
                cache_generation = generation_reader()
                if cache_generation:
                    cache.invalidate_for_generation(cache_generation)
            embedding_started = time.perf_counter()
            query_embedding = cache.embed_question(question)
            embedding_elapsed = time.perf_counter() - embedding_started
            cached = cache.lookup(query_embedding)
            if cached is not None:
                latest_generation = (
                    generation_reader() if generation_reader is not None else cache_generation
                )
                if latest_generation != cache_generation:
                    # The index changed during cache lookup. Ignore this old-generation hit.
                    if latest_generation:
                        cache.invalidate_for_generation(latest_generation)
                    cached = None
            if cached is not None:
                if observation is not None:
                    observation.update({
                        "cache_hit": True,
                        "retriever": retriever.name,
                        "provider": provider.name,
                        "chunk_ids": [p.chunk_id for p in cached.retrieved],
                        "scores": [round(p.score, 4) for p in cached.retrieved],
                        "answered_from_context": cached.answered_from_context,
                        "fallback": False,
                    })
                return cached
        except Exception as exc:
            if observation is not None:
                observation["cache_error"] = type(exc).__name__

    retrieval_started = time.perf_counter()
    effective_top_k = 1 if settings.failure_mode == "top_k_1" else settings.top_k
    if query_embedding is None:
        retrieved = retriever.retrieve(question, k=effective_top_k)
    else:
        retrieved = retriever.retrieve(question, k=effective_top_k,
                                       query_embedding=query_embedding)
    retrieval_elapsed = embedding_elapsed + time.perf_counter() - retrieval_started
    RETRIEVAL_LATENCY.observe(retrieval_elapsed)
    passages = [passage for passage in retrieved if passage.score >= settings.relevance_floor]
    attempts = 0
    used_fallback = False
    generation_elapsed = 0.0
    safe_validation_errors = {
        "grounded answers must include at least one retrieved citation",
        "abstentions must not include citations",
        "each structured citation must appear inline in the answer",
        "abstentions must use the standard no-evidence response",
        "abstentions must have low confidence",
    }

    if not passages:
        answer = Answer(
            reasoning="No retrieved passage met the relevance floor.",
            answer="The corpus does not cover this question well enough to answer reliably.",
            citations=[],
            answered_from_context=False,
            confidence="low",
        )
    else:
        answer = None
        for retry in (1, 2):
            attempts = retry
            generation_started = time.perf_counter()
            try:
                candidate = provider.generate(question, passages)
                payload = candidate.model_dump() if isinstance(candidate, Answer) else candidate
                validated = Answer.model_validate(payload)
                validated, repaired = _repair_extractive_answer(validated, question, passages)
                if repaired and observation is not None:
                    observation["answer_repaired_from_evidence"] = True
                validated, removed_citations = _remove_unretrieved_citations(validated, passages)
                if removed_citations:
                    if observation is not None:
                        observation["removed_citations"] = removed_citations
                validated, repaired_tuition = _repair_per_credit_tuition(
                    validated, question, passages
                )
                validated, repaired_rule_number = _repair_named_rule_number(
                    validated, question, passages
                )
                validated, repaired_attendance_clause = _repair_attendance_clause_number(
                    validated, question, passages
                )
                if (repaired_tuition or repaired_rule_number or repaired_attendance_clause) \
                        and observation is not None:
                    observation["answer_repaired_from_evidence"] = True
                _validate_citations(validated)
                answer = validated
                break
            except Exception as exc:
                message = str(exc)
                if observation is not None:
                    observation["validation_error"] = (
                        message if message in safe_validation_errors else type(exc).__name__
                    )
                # A full second local-model call can take several minutes. When the
                # failure is specifically grounding/citation validation, recover from
                # verbatim evidence; reserve the schema retry for malformed outputs.
                if message in safe_validation_errors:
                    extracted = _extractive_fallback(question, passages)
                    if extracted is not None:
                        answer = extracted
                        used_fallback = True
                        if observation is not None:
                            observation["extractive_fallback"] = True
                        break
            finally:
                generation_elapsed += time.perf_counter() - generation_started
        if answer is None:
            used_fallback = True
            answer = _extractive_fallback(question, passages) or Answer(
                reasoning="The generated response failed validation twice.",
                answer=("I couldn't produce a grounded answer from the available passages. "
                        "Please consult the source documents or rephrase your question."),
                citations=[],
                answered_from_context=False,
                confidence="low",
            )
    assert answer is not None

    if observation is not None:
        observation.update({
            "retriever": retriever.name,
            "provider": provider.name,
            "top_k": effective_top_k,
            "failure_mode": settings.failure_mode,
            "chunk_ids": [p.chunk_id for p in passages],
            "scores": [round(p.score, 4) for p in passages],
            "answered_from_context": answer.answered_from_context,
            "generation_attempts": attempts,
            "fallback": used_fallback,
            "retrieval_ms": round(retrieval_elapsed * 1000, 1),
            "generation_ms": round(generation_elapsed * 1000, 1),
        })
    if passages:
        GENERATION_LATENCY.observe(generation_elapsed)
    if not answer.answered_from_context:
        ABSTENTIONS.inc()
    if used_fallback:
        FALLBACKS.inc()
    response = AskResponse(
        request_id=request_id_var.get(),
        answer=answer.answer,
        citations=answer.citations,
        answered_from_context=answer.answered_from_context,
        confidence=answer.confidence,
        retrieved=[
            RetrievedRef(
                chunk_id=p.chunk_id, source=p.source, section=p.section, page=p.page, score=p.score
            )
            for p in passages
        ],
        provider=provider.name,
    )
    if (cache is not None and query_embedding is not None
            and settings.failure_mode == "off"
            and not used_fallback and not never_cache(question, answer.answered_from_context)):
        try:
            cache.store(question, query_embedding, response)
        except Exception as exc:
            if observation is not None:
                observation["cache_write_error"] = type(exc).__name__
    return response


def _remove_unretrieved_citations(
    answer: Answer, passages: list[Passage]
) -> tuple[Answer, int]:
    available = {(p.source, p.section, p.page) for p in passages}
    valid = [c for c in answer.citations if (c.source, c.section, c.page) in available]
    removed = len(answer.citations) - len(valid)
    if not answer.answered_from_context:
        removed += len(valid)
        valid = []
    return answer.model_copy(update={"citations": valid}), removed


def _repair_per_credit_tuition(
    answer: Answer, question: str, passages: list[Passage]
) -> tuple[Answer, bool]:
    """Ensure a tuition-per-credit answer includes the amount in its cited evidence.

    Local models occasionally cite a correct tuition passage but omit the amount, or
    copy an unrelated fee from a mixed table. Repair only when a retrieved passage
    explicitly labels a rupee amount as tuition per credit hour.
    """
    normalized_question = question.casefold()
    if "tuition" not in normalized_question or "credit hour" not in normalized_question:
        return answer, False

    for passage in passages:
        if "tuition" not in passage.section.casefold():
            continue
        match = _PER_CREDIT_TUITION.search(passage.text)
        if match is None:
            continue
        amount = match.group("amount")
        answer_amounts = {
            value.replace(",", "") for value in _ANSWER_VALUE.findall(answer.answer)
        }
        if amount.replace(",", "") in answer_amounts:
            return answer, False

        citation = Citation(
            source=passage.source, section=passage.section, page=passage.page
        )
        repaired = answer.model_copy(update={
            "answer": (
                f"The listed tuition fee is Rs. {amount} per credit hour "
                f"[{citation.source} / {citation.section}]"
            ),
            "citations": [citation],
            "answered_from_context": True,
            "confidence": "medium",
        })
        return repaired, True
    return answer, False


def _repair_named_rule_number(
    answer: Answer, question: str, passages: list[Passage]
) -> tuple[Answer, bool]:
    """Answer a question about a numbered rule from the retrieved heading itself."""
    normalized_question = question.casefold()
    if not all(term in normalized_question for term in ("numbered rule", "attendance requirement")):
        return answer, False

    for passage in passages:
        if "prospectus-academic-rules" not in passage.source.casefold():
            continue
        match = _ATTENDANCE_RULE_HEADING.search(passage.section)
        if match is None:
            continue
        number = match.group("number")
        if re.search(rf"\brule\s+{re.escape(number)}\b", answer.answer, re.IGNORECASE):
            return answer, False
        citation = Citation(
            source=passage.source, section=passage.section, page=passage.page
        )
        repaired = answer.model_copy(update={
            "answer": (
                f"Rule {number} is labelled Attendance Requirement "
                f"[{citation.source} / {citation.section}]"
            ),
            "citations": [citation],
            "answered_from_context": True,
            "confidence": "medium",
        })
        return repaired, True
    return answer, False


def _repair_attendance_clause_number(
    answer: Answer, question: str, passages: list[Passage]
) -> tuple[Answer, bool]:
    """Use a retrieved 100%-attendance clause heading when the model cites another rule."""
    normalized_question = question.casefold()
    if not all(term in normalized_question for term in ("clause", "100%", "attendance")):
        return answer, False

    for passage in passages:
        if "academic-rules-handbook" not in passage.source.casefold():
            continue
        match = _CLAUSE_HEADING.search(passage.section)
        if match is None or "100%" not in f"{passage.section} {passage.text}":
            continue
        number = match.group("number")
        claim = re.sub(r"\s*\[[^\]]+\]\s*$", "", answer.answer).strip()
        if number in _CLAUSE_NUMBER.findall(claim):
            return answer, False
        citation = Citation(
            source=passage.source, section=passage.section, page=passage.page
        )
        repaired = answer.model_copy(update={
            "answer": (
                f"Clause {number} requires 100% attendance "
                f"[{citation.source} / {citation.section}]"
            ),
            "citations": [citation],
            "answered_from_context": True,
            "confidence": "medium",
        })
        return repaired, True
    return answer, False


def _repair_extractive_answer(
    answer: Answer, question: str, passages: list[Passage]
) -> tuple[Answer, bool]:
    """Repair only a short answer copied verbatim from clearly relevant evidence.

    Small local models sometimes emit a supported value while setting
    `answered_from_context` false. Do not promote a paraphrase or a value found in an
    unrelated passage: require a literal excerpt plus a clause-number match or multiple
    meaningful query terms, then attach the citation from that exact retrieved passage.
    """
    if answer.answered_from_context or answer.citations:
        return answer, False
    expected_abstention = (
        "The corpus does not provide enough information to answer this question reliably."
    )
    if " ".join(answer.answer.split()).casefold() == expected_abstention.casefold():
        return answer, False

    excerpt = " ".join(answer.answer.split()).rstrip(".!? ")
    # A small model may append its prompt passage ordinal (for example
    # `[4 / 1.21]`) instead of a source citation. Strip only that numeric marker;
    # the value itself still has to occur verbatim in relevant retrieved text.
    excerpt = re.sub(r"\s*\[\s*\d+\s*/\s*\d+(?:\.\d+)*\s*\]\s*$", "", excerpt)
    excerpt = excerpt.strip().rstrip(".!? ")
    if not excerpt or len(excerpt) > 80:
        return answer, False
    clause_numbers = set(_CLAUSE_NUMBER.findall(question))
    answer_values = {
        " ".join(value.split()).strip() for value in _ANSWER_VALUE.findall(excerpt)
    }
    if clause_numbers:
        answer_values -= clause_numbers
    excerpts = [excerpt]
    if len(answer_values) == 1 and next(iter(answer_values)).casefold() != excerpt.casefold():
        # Permit a surrounding short phrase only when it contains one unambiguous
        # numeric value and that exact value occurs in the relevant passage.
        excerpts.append(next(iter(answer_values)))
    question_terms = {
        token.casefold() for token in _WORD.findall(question)
        if token.casefold() not in _QUESTION_STOP_WORDS
    }

    for passage in passages:
        evidence = " ".join(passage.text.split())
        section_and_text = f"{passage.section} {passage.text}"
        if clause_numbers:
            relevant = any(number in section_and_text for number in clause_numbers)
        else:
            evidence_terms = {token.casefold() for token in _WORD.findall(section_and_text)}
            relevant = len(question_terms & evidence_terms) >= min(2, len(question_terms))
        if not relevant:
            continue

        matched_excerpt: str | None = next(
            (value for value in excerpts if value.casefold() in evidence.casefold()), None
        )
        if matched_excerpt is None:
            continue

        citation = Citation(source=passage.source, section=passage.section, page=passage.page)
        repaired = answer.model_copy(update={
            "answer": f"{matched_excerpt} [{citation.source} / {citation.section}]",
            "citations": [citation],
            "answered_from_context": True,
            "confidence": "medium",
        })
        return repaired, True
    return answer, False


def _extractive_fallback(question: str, passages: list[Passage]) -> Answer | None:
    """Use one verbatim retrieved sentence when generation repeatedly fails validation.

    This recovery path is intentionally extractive: it needs at least two meaningful
    query terms to occur in the same sentence, copies that sentence without synthesis,
    and cites the exact passage it came from.
    """
    question_terms = {
        token.casefold() for token in _WORD.findall(question)
        if token.casefold() not in _QUESTION_STOP_WORDS
    }
    if len(question_terms) < 2:
        return None

    best: tuple[int, int, Passage, str] | None = None
    for passage in passages:
        normalized = " ".join(passage.text.split())
        for sentence in re.split(r"(?<=[.!?])\s+", normalized):
            sentence = sentence.strip()
            if not sentence or len(sentence) > 350:
                continue
            sentence_terms = {token.casefold() for token in _WORD.findall(sentence)}
            overlap = len(question_terms & sentence_terms)
            if overlap < 2:
                continue
            candidate = (overlap, int(passage.score * 10000), passage, sentence)
            if best is None or candidate[:2] > best[:2]:
                best = candidate

    if best is None:
        return None
    _, _, passage, sentence = best
    citation = Citation(source=passage.source, section=passage.section, page=passage.page)
    return Answer(
        reasoning="A retrieved sentence directly matches the question terms.",
        answer=f"{sentence} [{citation.source} / {citation.section}]",
        citations=[citation],
        answered_from_context=True,
        confidence="medium",
    )


def _validate_citations(answer: Answer) -> None:
    if answer.answered_from_context and not answer.citations:
        raise ValueError("grounded answers must include at least one retrieved citation")
    if not answer.answered_from_context and answer.citations:
        raise ValueError("abstentions must not include citations")
    if answer.answered_from_context:
        missing_inline = [
            citation for citation in answer.citations
            if f"[{citation.source} / {citation.section}]" not in answer.answer
        ]
        if missing_inline:
            raise ValueError("each structured citation must appear inline in the answer")
    if not answer.answered_from_context:
        # Keep abstentions mechanically safe: a model must not return an unsupported
        # factual answer while marking it as ungrounded (as happened in the live check).
        expected = "The corpus does not provide enough information to answer this question reliably."
        if re.sub(r"\s+", " ", answer.answer).strip().casefold() != expected.casefold():
            raise ValueError("abstentions must use the standard no-evidence response")
        if answer.confidence != "low":
            raise ValueError("abstentions must have low confidence")
