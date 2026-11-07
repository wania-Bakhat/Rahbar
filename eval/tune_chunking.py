#!/usr/bin/env python3
"""Compare chunk sizes and overlaps against a golden set using temporary Chroma indexes.

Example:
    python eval/tune_chunking.py --corpus corpus/raw --golden eval/golden.yaml

Each run creates and deletes its own temporary collection. The configured production
collection is not modified.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEXER_DIR = ROOT / "indexer"
for import_path in (str(ROOT), str(INDEXER_DIR)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from api.app.config import Settings, get_settings as get_api_settings  # noqa: E402
from api.app.embeddings import embed_text  # noqa: E402
from api.app.retrieval.chroma import ChromaRetriever  # noqa: E402
from eval.run_eval import load_golden, recall_at_k  # noqa: E402
from indexer.pipeline.chunk import chunk  # noqa: E402
from indexer.pipeline.clean import clean  # noqa: E402
from indexer.pipeline.config import (  # noqa: E402
    IndexerSettings,
    get_settings as get_indexer_settings,
)
from indexer.pipeline.embed import embed  # noqa: E402
from indexer.pipeline.extract import extract  # noqa: E402
from indexer.pipeline.run import discover  # noqa: E402
from indexer.pipeline.store import get_client  # noqa: E402

DEFAULT_CONFIGS = ((200, 25), (400, 50), (600, 75))


def parse_configs(value: str) -> list[tuple[int, int]]:
    configs: list[tuple[int, int]] = []
    for item in value.split(","):
        try:
            size_text, overlap_text = item.strip().split(":", maxsplit=1)
            size, overlap = int(size_text), int(overlap_text)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"invalid config {item!r}; expected SIZE:OVERLAP"
            ) from exc
        if size < 1 or overlap < 0 or overlap >= size:
            raise argparse.ArgumentTypeError(
                f"invalid config {item!r}; require size > 0 and 0 <= overlap < size"
            )
        configs.append((size, overlap))
    if len(configs) != 3:
        raise argparse.ArgumentTypeError("provide exactly three SIZE:OVERLAP configs")
    if len(set(configs)) != 3:
        raise argparse.ArgumentTypeError("the three chunking configs must be distinct")
    return configs


def validate_golden(questions: list[dict]) -> None:
    placeholders = [
        str(question.get("id", "?"))
        for question in questions
        if "TODO" in str(question.get("question", "")).upper()
    ]
    if placeholders:
        raise ValueError(
            "replace TODO questions in eval/golden.yaml before tuning; placeholders: "
            + ", ".join(placeholders)
        )
    missing_relevance = [
        str(question.get("id", "?"))
        for question in questions
        if not question.get("must_abstain", False) and not question.get("relevant")
    ]
    if missing_relevance:
        raise ValueError(
            "add relevant source/section pairs before tuning; missing for: "
            + ", ".join(missing_relevance)
        )


def build_chunks(
    corpus_dir: Path, settings: IndexerSettings, size: int, overlap: int
):
    documents = discover(str(corpus_dir))
    if not documents:
        raise ValueError(f"no indexable documents found in {corpus_dir}")
    chunks = []
    for path, doc_version, superseded in documents:
        if not path.is_file():
            raise FileNotFoundError(f"corpus document listed but missing: {path}")
        document = clean(extract(str(path), doc_version, superseded))
        chunks.extend(chunk(document, size, overlap))
    if not chunks:
        raise ValueError(f"no chunks produced from {corpus_dir} at size={size}")
    return chunks


def write_temporary_collection(
    client,
    collection_name: str,
    chunks,
    vectors: list[list[float]],
    embed_model: str,
) -> None:
    dimensions = {len(vector) for vector in vectors}
    if len(vectors) != len(chunks) or len(dimensions) != 1:
        raise ValueError("embedding service returned inconsistent vector dimensions")
    collection = client.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine", "embed_model": embed_model,
                  "dimension": next(iter(dimensions))},
    )
    for start in range(0, len(chunks), 500):
        batch = chunks[start:start + 500]
        collection.upsert(
            ids=[item.id for item in batch],
            documents=[item.text for item in batch],
            embeddings=vectors[start:start + 500],
            metadatas=[item.metadata() for item in batch],
        )


def evaluate_config(
    questions: list[dict],
    corpus_dir: Path,
    size: int,
    overlap: int,
    indexer_settings: IndexerSettings,
    api_settings: Settings,
    chroma_client,
    run_id: str,
    config_number: int,
) -> dict[str, int | float | None]:
    chunks = build_chunks(corpus_dir, indexer_settings, size, overlap)
    vectors = embed([item.text for item in chunks], indexer_settings)
    if len(vectors) != len(chunks):
        raise ValueError(f"expected {len(chunks)} embeddings, received {len(vectors)}")

    collection_name = f"rt-{run_id}-{config_number}"
    write_temporary_collection(
        chroma_client, collection_name, chunks, vectors, indexer_settings.embed_model
    )
    try:
        retriever_settings = replace(api_settings, collection=collection_name)
        retriever = ChromaRetriever(retriever_settings)
        recalls3: list[float] = []
        recalls5: list[float] = []
        for question in questions:
            text = str(question["question"])
            query_vector = embed_text(text, api_settings)
            retrieved = retriever.retrieve(text, 5, query_embedding=query_vector)
            retrieved_rows = [passage.model_dump() for passage in retrieved]
            relevant = question.get("relevant") or []
            score3 = recall_at_k(relevant, retrieved_rows, 3)
            score5 = recall_at_k(relevant, retrieved_rows, 5)
            if score3 is not None:
                recalls3.append(score3)
            if score5 is not None:
                recalls5.append(score5)
        return {
            "size": size,
            "overlap": overlap,
            "recall_at_3": sum(recalls3) / len(recalls3) if recalls3 else None,
            "recall_at_5": sum(recalls5) / len(recalls5) if recalls5 else None,
            "chunks": len(chunks),
        }
    finally:
        chroma_client.delete_collection(collection_name)


def print_table(rows: list[dict[str, int | float | None]]) -> None:
    print("\n| Size (tokens) | Overlap (tokens) | Recall@3 | Recall@5 | Chunks |")
    print("| ---: | ---: | ---: | ---: | ---: |")
    for row in rows:
        recall3 = row["recall_at_3"]
        recall5 = row["recall_at_5"]
        r3 = "n/a" if recall3 is None else f"{float(recall3):.3f}"
        r5 = "n/a" if recall5 is None else f"{float(recall5):.3f}"
        print(f"| {row['size']} | {row['overlap']} | {r3} | {r5} | {row['chunks']} |")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, default=ROOT / "corpus" / "raw",
                        help="corpus folder to index for each configuration")
    parser.add_argument("--golden", type=Path, default=ROOT / "eval" / "golden.yaml",
                        help="golden questions with verified relevant source/section pairs")
    parser.add_argument("--configs", type=parse_configs,
                        default=list(DEFAULT_CONFIGS),
                        help="exactly three SIZE:OVERLAP pairs, e.g. 200:25,400:50,600:75")
    args = parser.parse_args()

    try:
        questions = load_golden(args.golden)
        validate_golden(questions)
        indexer_settings = get_indexer_settings()
        api_settings = get_api_settings()
        # Prefer the selected CLI corpus path over CORPUS_DIR for local tuning.
        indexer_settings = replace(indexer_settings, corpus_dir=str(args.corpus))
        client = get_client(indexer_settings)
        run_id = uuid.uuid4().hex[:8]
        results = [
            evaluate_config(questions, args.corpus, size, overlap, indexer_settings,
                            api_settings, client, run_id, index)
            for index, (size, overlap) in enumerate(args.configs, start=1)
        ]
    except Exception as exc:
        print(f"chunk tuning failed: {exc}", file=sys.stderr)
        return 1

    print_table(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
