"""The contracts. Change them only with your partner's review: the UI, the
evaluation script and your tests all depend on these shapes.

`Answer` is what the model must produce (section 3.4). `AskResponse` is what
the API returns to the UI and to eval/run_eval.py. The model's `reasoning` is
never sent to the user.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class Passage(BaseModel):
    """One retrieved chunk, as the retriever hands it to the generator."""

    chunk_id: str
    text: str
    source: str
    section: str
    page: int | None = None
    score: float = Field(description="Similarity, higher is closer (1 - cosine distance).")


class Citation(BaseModel):
    source: str
    section: str
    page: int | None = None


class Answer(BaseModel):
    """The model's output contract. Send its JSON schema to the model, then validate."""

    reasoning: str = Field(description="Brief evidence summary; never private step-by-step reasoning.")
    answer: str = Field(
        description=(
            "Direct response grounded only in retrieved evidence. Every factual answer "
            "must include an inline citation formatted exactly [source / section]."
        )
    )
    citations: list[Citation] = Field(
        description=(
            "Structured citations copied exactly from retrieved passages. Must be empty "
            "when answered_from_context is false."
        )
    )
    answered_from_context: bool = Field(
        description=(
            "True when retrieved evidence directly supports the answer. False only when "
            "the corpus does not provide enough information; in that case use the standard "
            "no-evidence response and no citations."
        )
    )
    confidence: Literal["high", "medium", "low"] = Field(
        description="Confidence in the evidence-grounded answer; abstentions must be low."
    )


class RetrievedRef(BaseModel):
    """What the response says was retrieved. eval/run_eval.py scores against this."""

    chunk_id: str
    source: str
    section: str
    page: int | None = None
    score: float


class AskResponse(BaseModel):
    request_id: str
    answer: str
    citations: list[Citation]
    answered_from_context: bool
    confidence: Literal["high", "medium", "low"]
    retrieved: list[RetrievedRef]
    provider: str
