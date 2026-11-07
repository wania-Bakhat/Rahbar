#!/usr/bin/env python3
"""Score a running RAHBAR against a golden set, and gate CI on the result (section 5).

    python eval/run_eval.py --api http://<ingress>                 # your corpus
    python eval/run_eval.py --api ... --golden eval/fixtures/golden.fixture.yaml
    python eval/run_eval.py --api ... --update-baseline            # after a deliberate improvement

Exit code 0 when every gate passes, 1 when any fails. CI relies on that exit code.

Given: talking to the API, reading the golden set, writing results.json, the exit
code. Yours: the four functions marked STARTER-TODO. They are the evaluation.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx
import yaml

HERE = Path(__file__).resolve().parent

# The gate from section 5.4. Change these only with a reason written in docs/PIPELINE.md.
MAX_RECALL5_DROP = 0.05        # recall@5 may fall at most 5 points below the baseline
MIN_CITATION_VALIDITY = 0.95   # at least 95% of citations must match retrieved passages


def load_golden(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    questions = data.get("questions") or []
    if not questions:
        sys.exit(f"no questions in {path}")
    return questions


def ask(client: httpx.Client, api: str, question: str) -> dict:
    """POST one question and return the AskResponse as a dict (see api/app/schemas.py)."""
    response = client.post(f"{api.rstrip('/')}/api/ask", json={"question": question})
    response.raise_for_status()
    return response.json()


def recall_at_k(relevant: list[dict], retrieved: list[dict], k: int) -> float | None:
    """Fraction of the relevant (source, section) pairs found in the top k retrieved.
    Return None when the question has no relevant passages (must-abstain questions)."""
    relevant_pairs = {
        (str(item.get("source", "")), str(item.get("section", "")))
        for item in relevant
        if item.get("source") is not None and item.get("section") is not None
    }
    if not relevant_pairs:
        return None
    retrieved_pairs = {
        (str(item.get("source", "")), str(item.get("section", "")))
        for item in retrieved[:max(0, k)]
        if item.get("source") is not None and item.get("section") is not None
    }
    return len(relevant_pairs & retrieved_pairs) / len(relevant_pairs)


def citation_validity(response: dict) -> float | None:
    """Fraction of the response's citations that match a passage in response['retrieved'].
    Return None when there are no citations."""
    valid, total = citation_counts(response)
    if not total:
        return None
    return valid / total


def citation_counts(response: dict) -> tuple[int, int]:
    """Count citations matching a retrieved source, section, and page exactly."""
    retrieved = {
        (str(item.get("source", "")), str(item.get("section", "")), item.get("page"))
        for item in response.get("retrieved", [])
    }
    citations = response.get("citations", [])
    valid = sum(
        (str(citation.get("source", "")), str(citation.get("section", "")),
         citation.get("page")) in retrieved
        for citation in citations
    )
    return valid, len(citations)


def summarise(rows: list[dict]) -> dict:
    """Overall recall@3, recall@5, citation validity and abstention correctness, plus
    recall@5 broken down by question type. This dict becomes results.json."""
    recall3_values: list[float] = []
    recall5_values: list[float] = []
    citation_valid = 0
    citation_total = 0
    abstention_total = 0
    abstention_correct = 0
    must_abstain_failures: list[str] = []
    by_type: dict[str, list[dict]] = {}

    for row in rows:
        response = row.get("response") or {}
        relevant = row.get("relevant") or []
        retrieved = response.get("retrieved") or []
        row["recall_at_3"] = recall_at_k(relevant, retrieved, 3)
        row["recall_at_5"] = recall_at_k(relevant, retrieved, 5)
        if row["recall_at_3"] is not None:
            recall3_values.append(row["recall_at_3"])
        if row["recall_at_5"] is not None:
            recall5_values.append(row["recall_at_5"])
        kind = str(row.get("type", "ordinary"))
        by_type.setdefault(kind, []).append(row)

        valid_count, total_count = citation_counts(response)
        citation_valid += valid_count
        citation_total += total_count

        if row.get("must_abstain", False):
            abstention_total += 1
            if response.get("answered_from_context") is False:
                abstention_correct += 1
            else:
                must_abstain_failures.append(str(row.get("id", "unknown")))

    type_results: dict[str, dict[str, float | int | None]] = {}
    for kind, type_rows in sorted(by_type.items()):
        type_recall3 = [row["recall_at_3"] for row in type_rows
                        if row["recall_at_3"] is not None]
        type_recall5 = [row["recall_at_5"] for row in type_rows
                        if row["recall_at_5"] is not None]
        type_results[kind] = {
            "questions": len(type_rows),
            "answerable_questions": len(type_recall5),
            "recall_at_3": sum(type_recall3) / len(type_recall3) if type_recall3 else None,
            "recall_at_5": sum(type_recall5) / len(type_recall5) if type_recall5 else None,
        }

    return {
        "recall_at_3": sum(recall3_values) / len(recall3_values) if recall3_values else None,
        "recall_at_5": sum(recall5_values) / len(recall5_values) if recall5_values else None,
        "by_type": type_results,
        "citation_validity": citation_valid / citation_total if citation_total else None,
        "citation_valid": citation_valid,
        "citation_total": citation_total,
        "abstention_correctness": (
            abstention_correct / abstention_total if abstention_total else None
        ),
        "must_abstain_correct": abstention_correct,
        "must_abstain_total": abstention_total,
        "must_abstain_failures": must_abstain_failures,
    }


def gate(results: dict, baseline: dict | None) -> list[str]:
    """Return one message per failed gate (section 5.4); an empty list means pass."""
    failures: list[str] = []
    current_recall5 = results.get("recall_at_5")
    baseline_recall5 = baseline.get("recall_at_5") if baseline else None
    if baseline_recall5 is not None:
        if current_recall5 is None:
            failures.append("recall@5 is unavailable while a baseline value exists")
        elif float(current_recall5) < float(baseline_recall5) - MAX_RECALL5_DROP:
            failures.append(
                f"recall@5 dropped from baseline {float(baseline_recall5):.3f} to "
                f"{float(current_recall5):.3f} (more than {MAX_RECALL5_DROP:.0%})"
            )

    abstain_failures = results.get("must_abstain_failures") or []
    if abstain_failures:
        failures.append(
            "must-abstain questions answered from context: " + ", ".join(abstain_failures)
        )

    citation_validity_value = results.get("citation_validity")
    if (citation_validity_value is None
            or float(citation_validity_value) < MIN_CITATION_VALIDITY):
        actual = (
            "unavailable" if citation_validity_value is None
            else f"{float(citation_validity_value):.1%}"
        )
        failures.append(
            f"citation validity {actual} is below the required {MIN_CITATION_VALIDITY:.0%}"
        )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate RAHBAR against a golden set.")
    parser.add_argument("--api", required=True, help="base URL, e.g. http://192.168.49.2")
    parser.add_argument("--host", help="Host header, when your Ingress rule names a host")
    parser.add_argument("--golden", type=Path, default=HERE / "golden.yaml")
    parser.add_argument("--baseline", type=Path, default=HERE / "baseline.json")
    parser.add_argument("--out", type=Path, default=HERE / "results.json")
    parser.add_argument("--update-baseline", action="store_true",
                        help="write these results as the new baseline")
    args = parser.parse_args()

    questions = load_golden(args.golden)
    rows = []
    headers = {"Host": args.host} if args.host else {}
    with httpx.Client(timeout=120.0, headers=headers) as client:
        for q in questions:
            started = time.perf_counter()
            response = ask(client, args.api, q["question"])
            rows.append({
                "id": q["id"], "type": q.get("type", "ordinary"),
                "must_abstain": bool(q.get("must_abstain", False)),
                "relevant": q.get("relevant") or [],
                "expect": q.get("expect"),
                "response": response,
                "seconds": round(time.perf_counter() - started, 2),
            })
            print(f"  {q['id']:<5} {rows[-1]['seconds']:>6.2f}s  {q['question'][:60]}")

    results = summarise(rows)
    baseline = json.loads(args.baseline.read_text()) if args.baseline.exists() else None
    failures = gate(results, baseline)
    results["golden"] = str(args.golden)
    results["questions"] = len(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nresults written to {args.out}")
    if args.update_baseline:
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"baseline updated: {args.baseline}")

    if failures:
        print("\nGATE FAILED")
        for message in failures:
            print(f"  - {message}")
        return 1
    print("\ngate passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
