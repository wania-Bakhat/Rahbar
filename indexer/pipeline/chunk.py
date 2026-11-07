"""Stage 3: Chunk. Structure-aware, with overlap."""

from __future__ import annotations

import hashlib
import re

from .models import Chunk, Document

_NUMBERED_HEADING = re.compile(r"^(?:\d+(?:\.\d+)*[.)]?\s+|section\s+\d+|chapter\s+\d+)", re.I)
_MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")


def _heading(line: str) -> str | None:
    match = _MARKDOWN_HEADING.match(line.strip())
    if match:
        return match.group(1).strip()
    value = line.strip()
    if not value or len(value) > 110 or len(value.split()) > 14:
        return None
    if _NUMBERED_HEADING.match(value):
        return value
    letters = [char for char in value if char.isalpha()]
    if len(letters) >= 4 and sum(char.isupper() for char in letters) / len(letters) >= 0.85:
        return value
    return None


def chunk(doc: Document, size: int, overlap: int) -> list[Chunk]:
    """Split on sections, then paragraphs, then sentences, keeping each chunk under
    `size` tokens, with `overlap` tokens shared between neighbours. Every chunk keeps
    the section heading it sits under, its page, doc_version and superseded."""
    if size < 1:
        raise ValueError("chunk size must be at least 1")
    if overlap < 0 or overlap >= size:
        raise ValueError("chunk overlap must be >= 0 and smaller than chunk size")

    chunks: list[Chunk] = []
    section = "Introduction"
    buffer: list[tuple[str, int]] = []

    def emit() -> None:
        nonlocal buffer
        if not buffer:
            return
        if chunks and len(buffer) <= overlap:
            buffer = []
            return
        text = " ".join(token for token, _ in buffer).strip()
        if text:
            ordinal = len(chunks) + 1
            digest = hashlib.sha256(
                f"{doc.source}\0{doc.doc_version}\0{ordinal}\0{text}".encode("utf-8")
            ).hexdigest()[:16]
            chunks.append(Chunk(
                id=f"{hashlib.sha256(doc.source.encode()).hexdigest()[:10]}-{ordinal:05d}-{digest}",
                text=text,
                source=doc.source,
                section=section,
                page=buffer[0][1],
                doc_version=doc.doc_version,
                superseded=doc.superseded,
            ))
        buffer = buffer[-overlap:] if overlap else []

    def add_tokens(tokens: list[str], page_number: int) -> None:
        nonlocal buffer
        cursor = 0
        while cursor < len(tokens):
            capacity = size - len(buffer)
            take = min(capacity, len(tokens) - cursor)
            buffer.extend((token, page_number) for token in tokens[cursor:cursor + take])
            cursor += take
            if len(buffer) == size and cursor < len(tokens):
                emit()
        # A paragraph boundary is a preferred boundary when there is room to
        # retain the requested overlap before the next paragraph.
        if len(buffer) >= size:
            emit()

    for page in doc.pages:
        paragraph: list[str] = []

        def flush_paragraph() -> None:
            if not paragraph:
                return
            text = " ".join(paragraph)
            sentences = re.split(r"(?<=[.!?])\s+", text)
            for sentence in sentences:
                words = sentence.split()
                if (buffer and len(buffer) > overlap
                        and len(buffer) + len(words) > size):
                    emit()
                add_tokens(words, page.page)
            paragraph.clear()

        for raw_line in page.text.splitlines():
            line = raw_line.strip()
            if not line:
                flush_paragraph()
                continue
            title = _heading(line)
            if title:
                flush_paragraph()
                emit()  # do not carry overlap across section boundaries
                buffer = []
                section = title
                paragraph.append(title)
            else:
                paragraph.append(line)
        flush_paragraph()
    if buffer:
        # Suppress a trailing chunk that contains only overlap copied from the
        # previous chunk.
        if len(chunks) and len(buffer) <= overlap:
            buffer = []
        else:
            emit()
    return chunks
