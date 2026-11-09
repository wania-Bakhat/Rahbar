from __future__ import annotations

from eval.run_eval import expected_value_present, gate, summarise


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
