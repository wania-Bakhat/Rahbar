"""Starter tests for the week-1 dummy index. No Chroma server needed: a fake
client records what the indexer would have written."""

from __future__ import annotations

import math
from pathlib import Path

from pipeline.clean import clean
from pipeline.chunk import chunk
from pipeline.config import get_settings
from pipeline.dummy import DUMMY_DIM, DUMMY_MODEL, fake_vector, write_dummy_index
from pipeline.models import Document, Page
from pipeline.run import discover


class FakeCollection:
    def __init__(self, name: str, metadata: dict) -> None:
        self.name, self.metadata, self.rows = name, metadata, {}

    def add(self, ids, documents, embeddings, metadatas) -> None:
        for i, d, e, m in zip(ids, documents, embeddings, metadatas):
            self.rows[i] = (d, e, m)

    def count(self) -> int:
        return len(self.rows)


class FakeClient:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}

    def delete_collection(self, name: str) -> None:
        if name not in self.collections:
            raise ValueError("no such collection")
        del self.collections[name]

    def create_collection(self, name: str, metadata: dict) -> FakeCollection:
        self.collections[name] = FakeCollection(name, metadata)
        return self.collections[name]


def test_dummy_index_writes_three_chunks_and_records_the_model() -> None:
    client = FakeClient()
    assert write_dummy_index(get_settings(), client) == 3
    col = client.collections["rahbar"]
    assert col.metadata["embed_model"] == DUMMY_MODEL
    assert col.metadata["dimension"] == DUMMY_DIM
    for _doc, vector, meta in col.rows.values():
        assert len(vector) == DUMMY_DIM
        assert set(meta) == {"source", "section", "page", "doc_version", "superseded"}


def test_dummy_index_can_run_twice() -> None:
    client = FakeClient()
    write_dummy_index(get_settings(), client)
    assert write_dummy_index(get_settings(), client) == 3


def test_fake_vectors_are_deterministic_unit_vectors() -> None:
    a, b = fake_vector("same text"), fake_vector("same text")
    assert a == b
    assert math.isclose(sum(v * v for v in a), 1.0, rel_tol=1e-9)


def test_discover_reads_fixture_front_matter() -> None:
    fixtures = Path(__file__).resolve().parents[2] / "eval" / "fixtures"
    found = {p.name: (version, old) for p, version, old in discover(str(fixtures))}
    assert found["academic-rules-2023.md"] == ("2023", True)
    assert found["academic-rules-2026.md"] == ("2026", False)


def test_clean_keeps_numbered_clause_even_when_it_repeats_at_page_edges() -> None:
    doc = Document("rules.pdf", "2026", False, pages=[
        Page("rules.pdf", 1, "Header\nAttendance Requirements\n"
             "1.21 Students must attend all scheduled classes.\nPage 1"),
        Page("rules.pdf", 2, "Header\nAttendance Requirements\n"
             "1.21 Students must attend all scheduled classes.\nPage 2"),
    ])

    clean(doc)

    assert "1.21 Students must attend all scheduled classes." in doc.pages[0].text
    assert "Attendance Requirements" not in doc.pages[0].text


def test_chunk_keeps_short_clause_content_that_is_no_longer_only_overlap() -> None:
    document = Document("rules.pdf", "2026", False, pages=[Page(
        "rules.pdf", 1,
        "Attendance Requirements\n"
        "1.21 Students are required to maintain 100% attendance in lectures and labs.\n"
        "Absence of a maximum of 20% may be condoned for genuine reasons.\n"
        "1.22 Failure to meet attendance renders a student ineligible for the final exam.\n"
        "The student will be assigned an F/A grade.",
    )])

    chunks = chunk(document, size=100, overlap=50)

    clause_121 = [item for item in chunks if item.section.startswith("1.21")]
    assert clause_121
    assert any("100% attendance" in item.text for item in clause_121)
