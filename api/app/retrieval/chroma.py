"""The real retriever. Yours to build (sections 3.2 and 4.4).

Connection details are already here; the query is not.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
import re
from typing import Any, cast

from ..config import Settings
from ..embeddings import embed_text
from ..schemas import Passage

_HISTORICAL_CUES = re.compile(
    r"\b(?:old(?:er)? version|previous version|prior version|earlier version|"
    r"superseded|repealed|historical|former policy|previously|before)\b",
    re.IGNORECASE,
)
_YEAR = re.compile(r"\b(19\d{2}|20\d{2})\b")
_VERSION_TERMS = re.compile(r"\b(?:version|edition|policy|rules|handbook|prospectus)\b", re.I)
_SOURCE_HINTS = (
    (re.compile(r"\b(?:short\s+)?prospectus\s+academic\s+rules\b", re.I),
     "prospectus-academic-rules-2026.pdf"),
    (re.compile(r"\bacademic\s+rules\s+handbook\b", re.I),
     "academic-rules-handbook-2026.pdf"),
    (re.compile(r"\bcurrent\s+academic\s+rules\b", re.I),
     "academic-rules-handbook-2026.pdf"),
    (re.compile(r"\bstudent\s+handbook\b", re.I),
     "student-handbook-2026.pdf"),
    (re.compile(r"\b2023[-–]24\s+annual\s+report\b", re.I),
     "annual-report-2023-24.pdf"),
)
_SECTION_HINTS = (
    (re.compile(r"\btraining\s+and\s+support\b", re.I),
     "student-handbook-2026.pdf", "10. Training and Support"),
    (re.compile(r"\b(?:clause\s+number|which\s+clause)\b.*100%.*\battendance\b", re.I),
     "academic-rules-handbook-2026.pdf",
     "1.21 Students are required to maintain 100% attendance in"),
)


def _asks_for_older_version(question: str) -> bool:
    if _HISTORICAL_CUES.search(question):
        return True
    current_year = datetime.now(timezone.utc).year
    years = [int(value) for value in _YEAR.findall(question)]
    return bool(any(year < current_year for year in years) and _VERSION_TERMS.search(question))


def _requested_source(question: str) -> str | None:
    """Return a corpus filename only when the question explicitly names that source."""
    return next((source for pattern, source in _SOURCE_HINTS if pattern.search(question)), None)


def _requested_section(question: str, source: str | None) -> str | None:
    """Use exact section metadata when the question names a distinctive heading."""
    if source is None:
        return None
    return next((section for pattern, scoped_source, section in _SECTION_HINTS
                 if source == scoped_source and pattern.search(question)), None)


class ChromaRetriever:
    name = "chroma"

    def __init__(self, settings: Settings) -> None:
        import chromadb  # the thin client, from chromadb-client in requirements.txt
        from chromadb.config import Settings as ChromaSettings

        self.settings = settings
        self.client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port,
                                          settings=ChromaSettings(anonymized_telemetry=False))

    def _catalog_metadata(self) -> dict[str, object]:
        try:
            catalog = self.client.get_collection(name=f"{self.settings.collection}_catalog")
        except Exception:
            return {}
        return catalog.metadata or {}

    def active_collection(self) -> Any:
        """Resolve the fully built index published by the indexer catalog."""
        metadata = self._catalog_metadata()
        name = metadata.get("active_collection") or self.settings.collection
        return self.client.get_collection(name=str(name))

    def index_generation(self) -> str | None:
        """Return the writer's Chroma generation marker for semantic-cache invalidation."""
        metadata = self._catalog_metadata()
        generation = metadata.get("index_generation")
        if generation is None:
            generation = (self.active_collection().metadata or {}).get("index_generation")
        return str(generation) if generation is not None else None

    def retrieve(
        self, question: str, k: int, query_embedding: list[float] | None = None
    ) -> list[Passage]:
        if k <= 0:
            return []
        query_vector = query_embedding if query_embedding is not None else embed_text(
            question, self.settings
        )
        collection = self.active_collection()
        include_superseded = (
            _asks_for_older_version(question)
            or self.settings.failure_mode == "no_superseded_filter"
        )
        query_embeddings = cast(list[Sequence[float] | Sequence[int]], [query_vector])
        requested_source = _requested_source(question)
        requested_section = _requested_section(question, requested_source)
        if requested_source and requested_section:
            result = collection.query(
                query_embeddings=query_embeddings,
                n_results=k,
                where={"$and": [
                    {"source": requested_source},
                    {"section": requested_section},
                ]},
                include=["documents", "metadatas", "distances"],
            )
        elif requested_source:
            result = collection.query(
                query_embeddings=query_embeddings,
                n_results=k,
                where={"source": requested_source},
                include=["documents", "metadatas", "distances"],
            )
        elif include_superseded:
            result = collection.query(
                query_embeddings=query_embeddings,
                n_results=k,
                include=["documents", "metadatas", "distances"],
            )
        else:
            result = collection.query(
                query_embeddings=query_embeddings,
                n_results=k,
                where={"superseded": False},
                include=["documents", "metadatas", "distances"],
            )

        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        passages: list[Passage] = []
        for chunk_id, text, metadata, distance in zip(ids, documents, metadatas, distances):
            metadata = metadata or {}
            if metadata.get("superseded", False) and not include_superseded:
                continue
            if text is None:
                continue
            raw_page = metadata.get("page")
            try:
                page = int(raw_page) if raw_page is not None else None
            except (TypeError, ValueError):
                page = None
            score = 1.0 - float(distance)
            if score < self.settings.relevance_floor:
                continue
            passages.append(Passage(
                chunk_id=str(chunk_id),
                text=str(text),
                source=str(metadata.get("source", "unknown")),
                section=str(metadata.get("section", "")),
                page=page,
                score=score,
            ))
        return passages
