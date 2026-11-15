"""A provider with no model and no network.

Use it for every unit test and for CI (section 6): your tests must never call a
real model. It is deterministic: the same input always gives the same output.
"""

from __future__ import annotations

import re

from ...schemas import Answer, Citation, Passage

_TOKEN = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_INSTRUCTION = re.compile(
    r"(?:ignore|disregard)\s+(?:all\s+)?(?:previous|prior|earlier)\s+instructions"
    r"\b[^.!?]*(?:[.!?]|$)|"
    r"treat\s+this\s+passage\s+as\s+a\s+command\b[^.!?]*(?:[.!?]|$)",
    re.IGNORECASE,
)
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "do", "does",
    "for", "from", "how", "i", "if", "in", "is", "it", "of", "on", "or",
    "the", "their", "this", "to", "was", "what", "when", "where", "which",
    "who", "why", "with", "now", "rules", "say", "ignore", "disregard",
    "earlier", "previous", "prior", "instructions", "student",
}


def _safe_evidence(passage: Passage) -> str:
    """Drop instruction-like sentences that appear inside retrieved source text."""
    text = _INSTRUCTION.sub("", passage.text)
    return " ".join(text.split())


def _tokens(text: str) -> set[str]:
    return {token.casefold() for token in _TOKEN.findall(text)}


class StubProvider:
    name = "stub"

    def generate(self, question: str, passages: list[Passage]) -> Answer:
        if not passages:
            return Answer(
                reasoning="stub: nothing was retrieved",
                answer="(stub) No passages were retrieved for this question.",
                citations=[],
                answered_from_context=False,
                confidence="low",
            )
        question_terms = _tokens(question) - _STOP_WORDS
        candidates = [
            (
                len(question_terms & _tokens(f"{passage.section} {evidence}")),
                passage.score,
                -index,
                passage,
                evidence,
            )
            for index, passage in enumerate(passages)
            if (evidence := _safe_evidence(passage))
        ]
        if not candidates:
            return Answer(
                reasoning="stub: retrieved text contained no usable evidence",
                answer="The corpus does not provide enough information to answer this question reliably.",
                citations=[],
                answered_from_context=False,
                confidence="low",
            )
        _, _, _, top, evidence = max(candidates, key=lambda item: item[:3])
        return Answer(
            reasoning="stub: cites the best-matching retrieved passage",
            answer=f"The retrieved evidence says: {evidence} [{top.source} / {top.section}]",
            citations=[Citation(source=top.source, section=top.section, page=top.page)],
            answered_from_context=True,
            confidence="low",
        )
