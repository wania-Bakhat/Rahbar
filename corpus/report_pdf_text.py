#!/usr/bin/env python3
"""Report PDF page counts and pages with no extractable text.

Usage:
    python corpus/report_pdf_text.py
    python corpus/report_pdf_text.py path/to/pdf-folder

Requires pypdf (included in indexer/requirements.txt).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pypdf import PdfReader


def inspect_pdf(path: Path) -> tuple[int, list[int]]:
    """Return page count and 1-based pages with no extractable text."""
    reader = PdfReader(path)
    pages_without_text = [
        page_number
        for page_number, page in enumerate(reader.pages, start=1)
        if not (page.extract_text() or "").strip()
    ]
    return len(reader.pages), pages_without_text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "directory",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parent / "raw",
        help="directory to scan (default: corpus/raw)",
    )
    args = parser.parse_args()

    if not args.directory.is_dir():
        print(f"error: not a directory: {args.directory}", file=sys.stderr)
        return 2

    pdfs = sorted(
        (path for path in args.directory.iterdir() if path.is_file() and path.suffix.lower() == ".pdf"),
        key=lambda path: path.name.lower(),
    )
    if not pdfs:
        print(f"No PDFs found in {args.directory}")
        return 0

    errors = 0
    print(f"PDFs in {args.directory}:\n")
    print(f"{'PDF':<70} {'Pages':>7}  Pages with no text")
    print(f"{'-' * 70} {'-' * 7}  {'-' * 24}")
    for path in pdfs:
        try:
            page_count, no_text_pages = inspect_pdf(path)
            pages = ", ".join(map(str, no_text_pages)) if no_text_pages else "none"
            print(f"{path.name:<70} {page_count:>7}  {pages}")
        except Exception as exc:
            errors += 1
            print(f"{path.name:<70} {'ERROR':>7}  {exc}")

    print(f"\nScanned {len(pdfs)} PDF(s); {errors} error(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
