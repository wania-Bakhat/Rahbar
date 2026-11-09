#!/usr/bin/env python3
"""Measure semantic-cache thresholds on labeled same/different-answer pairs."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_THRESHOLDS = (0.85, 0.90, 0.95)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def load_pairs(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    pairs = data.get("pairs") or []
    if len(pairs) < 3:
        raise ValueError("provide at least three labeled question pairs")
    for pair in pairs:
        if not all(pair.get(key) for key in ("id", "question_a", "question_b")):
            raise ValueError("each pair needs id, question_a, and question_b")
        if not isinstance(pair.get("same_answer"), bool):
            raise ValueError(f"pair {pair['id']} needs a boolean same_answer label")
    if not any(pair["same_answer"] for pair in pairs):
        raise ValueError("include at least one same-answer paraphrase")
    if not any(not pair["same_answer"] for pair in pairs):
        raise ValueError("include at least one different-answer pair")
    return pairs


def parse_thresholds(value: str) -> list[float]:
    try:
        thresholds = [float(item.strip()) for item in value.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("thresholds must be comma-separated numbers") from exc
    if len(thresholds) not in (2, 3) or len(set(thresholds)) != len(thresholds):
        raise argparse.ArgumentTypeError("compare exactly two or three distinct thresholds")
    if any(value < 0.0 or value > 1.0 for value in thresholds):
        raise argparse.ArgumentTypeError("thresholds must be between 0 and 1")
    return sorted(thresholds)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", type=Path, default=ROOT / "eval" / "cache-threshold-pairs.yaml")
    parser.add_argument("--thresholds", type=parse_thresholds, default=list(DEFAULT_THRESHOLDS))
    parser.add_argument("--ollama-url", default=os.environ.get("OLLAMA_URL", "http://localhost:11434"))
    parser.add_argument("--model", default=os.environ.get("EMBED_MODEL", "nomic-embed-text"))
    parser.add_argument("--out", type=Path, default=ROOT / "eval" / "cache-threshold-results.json")
    args = parser.parse_args()

    try:
        pairs = load_pairs(args.pairs)
        questions = sorted({
            question
            for pair in pairs
            for question in (pair["question_a"], pair["question_b"])
        })
        vectors: dict[str, list[float]] = {}
        with httpx.Client(timeout=httpx.Timeout(120.0, connect=15.0)) as client:
            for question in questions:
                response = client.post(
                    f"{args.ollama_url.rstrip('/')}/api/embed",
                    json={"model": args.model, "input": [question]},
                )
                response.raise_for_status()
                embeddings = response.json().get("embeddings")
                if not isinstance(embeddings, list) or len(embeddings) != 1:
                    raise ValueError("Ollama returned an invalid embedding response")
                vectors[question] = [float(value) for value in embeddings[0]]

        measured = []
        for pair in pairs:
            measured.append({
                **pair,
                "cosine_similarity": round(cosine_similarity(
                    vectors[pair["question_a"]], vectors[pair["question_b"]]
                ), 6),
            })

        threshold_results = []
        for threshold in args.thresholds:
            same = [row for row in measured if row["same_answer"]]
            different = [row for row in measured if not row["same_answer"]]
            hits = sum(row["cosine_similarity"] >= threshold for row in same)
            false_hits = [
                row["id"] for row in different if row["cosine_similarity"] >= threshold
            ]
            threshold_results.append({
                "threshold": threshold,
                "same_answer_hits": hits,
                "same_answer_pairs": len(same),
                "different_answer_false_hits": false_hits,
                "different_answer_pairs": len(different),
            })
        qualifying = [row["threshold"] for row in threshold_results
                      if not row["different_answer_false_hits"]]
        result = {
            "measured_at_utc": datetime.now(UTC).isoformat(),
            "embedding_model": args.model,
            "pairs_file": args.pairs.resolve().relative_to(ROOT).as_posix(),
            "pair_results": measured,
            "threshold_results": threshold_results,
            "lowest_threshold_with_zero_false_hits": min(qualifying) if qualifying else None,
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0 if qualifying else 1
    except Exception as exc:
        print(f"cache threshold experiment failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
