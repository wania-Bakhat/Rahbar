from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.run_eval import expected_value_present, gate, load_checkpoint_rows, summarise


def test_expected_value_matches_claim_text_not_citation_metadata() -> None:
    row = {
        "expect": "1.21",
        "response": {"answer": "The clause requires 1.21 [rules.pdf / 1.22 Other clause]"},
    }

    assert expected_value_present(row) is True


def test_integer_expected_value_does_not_match_part_of_clause_number() -> None:
    row = {"expect": "1", "response": {"answer": "The relevant clause is 1.21."}}

    assert expected_value_present(row) is False


def test_expected_value_gate_rejects_missing_exact_answer() -> None:
    results = {"expected_value_failures": ["q14"]}

    assert any("q14" in failure for failure in gate(results, None))


def test_summary_counts_expected_values() -> None:
    rows = [
        {"id": "q13", "expect": "1.22", "response": {"answer": "1.22"}},
        {"id": "q14", "expect": "2.00", "response": {"answer": "2.0"}},
    ]

    result = summarise(rows)

    assert result["expected_value_correct"] == 1
    assert result["expected_value_total"] == 2
    assert result["expected_value_failures"] == ["q14"]


def test_checkpoint_resume_accepts_only_a_matching_golden_prefix() -> None:
    checkpoint = Path(__file__).with_name(".checkpoint-test.json")
    rows = [{"id": "q01", "response": {"answer": "evidence"}}]
    try:
        checkpoint.write_text(json.dumps(rows), encoding="utf-8")
        assert load_checkpoint_rows(checkpoint, [{"id": "q01"}, {"id": "q02"}]) == rows
        with pytest.raises(ValueError, match="does not match"):
            load_checkpoint_rows(checkpoint, [{"id": "q02"}, {"id": "q03"}])
    finally:
        checkpoint.unlink(missing_ok=True)
