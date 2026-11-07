"""Stage 1: Extract. PDF (or HTML, or Markdown) to text, page by page."""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

from .models import Document
from .models import Page


class _HTMLText(HTMLParser):
    """Small standard-library HTML text extractor that keeps block boundaries."""

    BLOCKS = {"address", "article", "br", "dd", "div", "dt", "h1", "h2", "h3",
              "h4", "h5", "h6", "li", "p", "section", "tr"}
    SKIP = {"script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP:
            self.skip_depth += 1
        elif not self.skip_depth and tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self.skip_depth:
            self.skip_depth -= 1
        elif not self.skip_depth and tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)


def extract(path: str, doc_version: str, superseded: bool) -> Document:
    """Return the document's text page by page.

    Detect pages with no text layer and OCR them; mark those pages ocr=True.
    The OCR libraries need system packages in your Dockerfile (tesseract-ocr,
    poppler-utils), not only pip packages.
    """
    source = Path(path)
    suffix = source.suffix.lower()
    doc = Document(source.name, doc_version, superseded)

    if suffix == ".pdf":
        try:
            import pdfplumber
        except ImportError as exc:
            raise RuntimeError("PDF extraction requires pdfplumber; install indexer/requirements.txt") from exc

        with pdfplumber.open(source) as pdf:
            for number, pdf_page in enumerate(pdf.pages, start=1):
                text = pdf_page.extract_text() or ""
                ocr_used = not text.strip()
                if ocr_used:
                    try:
                        from pdf2image import convert_from_path
                        import pytesseract
                    except ImportError as exc:
                        raise RuntimeError(
                            f"page {number} of {source.name} has no text layer; OCR requires "
                            "pdf2image, pytesseract, Poppler, and Tesseract"
                        ) from exc
                    try:
                        image = convert_from_path(
                            str(source), first_page=number, last_page=number, dpi=300
                        )[0]
                        text = pytesseract.image_to_string(image)
                    except Exception as exc:
                        raise RuntimeError(f"OCR failed on {source.name} page {number}: {exc}") from exc
                doc.pages.append(Page(source.name, number, text, ocr=ocr_used))
        return doc

    if suffix in {".md", ".txt"}:
        text = source.read_text(encoding="utf-8", errors="replace")
        if suffix == ".md" and text.startswith("---\n"):
            _, separator, remainder = text[4:].partition("\n---")
            if separator:
                text = remainder.split("\n", 1)[-1]
        doc.pages.append(Page(source.name, 1, text))
        return doc

    if suffix in {".html", ".htm"}:
        parser = _HTMLText()
        parser.feed(source.read_text(encoding="utf-8", errors="replace"))
        doc.pages.append(Page(source.name, 1, "".join(parser.parts)))
        return doc

    raise ValueError(f"unsupported document type: {source}")
