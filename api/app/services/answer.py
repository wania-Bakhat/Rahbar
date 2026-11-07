"""Turns a question into an AskResponse. This is where the query pipeline lives.

The version below is the bare minimum that works with the stubs: retrieve,
generate, return. Section 3.2 lists eight steps; this file does two of them.
"""

from __future__ import annotations

import time

from ..config import Settings
from ..logjson import request_id_var, request_observation_var
from ..providers.llm.base import LLMProvider
from ..retrieval.base import Retriever
from ..schemas import Answer, AskResponse, Passage, RetrievedRef
from ..telemetry import (ABSTENTIONS, FALLBACKS, GENERATION_LATENCY,
                         RETRIEVAL_LATENCY)
from .cache import SemanticCache, is_follow_up

def answer_question(
    question: str, retriever: Retriever, provider: LLMProvider, settings: Settings,
    cache: SemanticCache | None = None,
) -> AskResponse:
    follow_up = is_follow_up(question)
    query_embedding: list[float] | None = None
    embedding_elapsed = 0.0
    observation = request_observation_var.get()
    if observation is not None:
        observation["cache_hit"] = False
        observation["follow_up"] = follow_up
    if cache is not None and not follow_up:
        try:
            embedding_started = time.perf_counter()
            query_embedding = cache.embed_question(question)
            embedding_elapsed = time.perf_counter() - embedding_started
            cached = cache.lookup(query_embedding)
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
    if query_embedding is None:
        retrieved = retriever.retrieve(question, k=settings.top_k)
    else:
        retrieved = retriever.retrieve(question, k=settings.top_k,
                                       query_embedding=query_embedding)
    retrieval_elapsed = embedding_elapsed + time.perf_counter() - retrieval_started
    RETRIEVAL_LATENCY.observe(retrieval_elapsed)
    passages = [passage for passage in retrieved if passage.score >= settings.relevance_floor]
    attempts = 0
    used_fallback = False
    generation_elapsed = 0.0

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
        for attempts in (1, 2):
            generation_started = time.perf_counter()
            try:
                candidate = provider.generate(question, passages)
                payload = candidate.model_dump() if isinstance(candidate, Answer) else candidate
                validated = Answer.model_validate(payload)
                validated, removed_citations = _remove_unretrieved_citations(validated, passages)
                if removed_citations:
                    if observation is not None:
                        observation["removed_citations"] = removed_citations
                _validate_citations(validated)
                answer = validated
                break
            except Exception as exc:
                if observation is not None:
                    observation["validation_error"] = type(exc).__name__
            finally:
                generation_elapsed += time.perf_counter() - generation_started
        if answer is None:
            used_fallback = True
            answer = Answer(
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
            "top_k": settings.top_k,
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
    if (cache is not None and query_embedding is not None and not follow_up
            and not used_fallback and answer.answered_from_context):
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


def _validate_citations(answer: Answer) -> None:
    if answer.answered_from_context and not answer.citations:
        raise ValueError("grounded answers must include at least one retrieved citation")
    if not answer.answered_from_context and answer.citations:
        raise ValueError("abstentions must not include citations")
