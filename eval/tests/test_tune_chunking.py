from __future__ import annotations

from pathlib import Path

from eval.tune_chunking import recorded_path


def test_recorded_path_is_relative_inside_repository() -> None:
    root = Path(__file__).resolve().parents[2]
    path = root / "corpus" / "raw"

    assert recorded_path(path, root) == "corpus/raw"


def test_recorded_path_keeps_external_mount_path() -> None:
    root = Path(__file__).resolve().parents[2]
    mounted_corpus = root.parent / "mounted-corpus"

    assert recorded_path(mounted_corpus, root) == mounted_corpus.as_posix()
