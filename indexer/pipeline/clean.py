"""Stage 2: Clean. Remove artefacts without destroying structure."""

from __future__ import annotations

import re
from collections import Counter

from .models import Document


def clean(doc: Document) -> Document:
    """Strip headers and footers that repeat on every page; keep headings and
    section boundaries, because chunking and citations depend on them."""
    # Repeated edge lines are likely running headers/footers. Only consider lines
    # in the first/last three positions so repeated body text remains untouched.
    edge_counts: Counter[str] = Counter()
    page_lines: dict[int, list[str]] = {}
    for page in doc.pages:
        lines = [re.sub(r"\s+", " ", line).strip() for line in page.text.splitlines()]
        page_lines[page.page] = lines
        candidates = {line.casefold() for line in lines[:3] + lines[-3:] if line}
        edge_counts.update(candidates)

    repeated_edges = {line for line, count in edge_counts.items() if count >= 2}
    page_number = re.compile(r"^(?:page\s+)?\d+(?:\s*(?:of|/)\s*\d+)?$", re.IGNORECASE)

    for page in doc.pages:
        lines = page_lines[page.page]
        cleaned: list[str] = []
        for index, line in enumerate(lines):
            normalized = line.casefold()
            is_edge = index < 3 or index >= len(lines) - 3
            if not line:
                if cleaned and cleaned[-1] != "":
                    cleaned.append("")
                continue
            if is_edge and normalized in repeated_edges:
                continue
            if is_edge and page_number.fullmatch(line):
                continue
            cleaned.append(line)
        page.text = "\n".join(cleaned).strip()
    return doc
