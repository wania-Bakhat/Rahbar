"""Stage 1: Extract. PDF (or HTML, or Markdown) to text, page by page."""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

from .models import Document
from .models import Page


_TWO_COLUMN_PDF_SPLITS = {
    # The prospectus fee page has policy prose on the left and two tables on the
    # right. Full-page reading order interleaves those columns and associates the
    # wrong fee with the tuition sentence. Keep this exception source-specific.
    "prospectus-fee-information-2026.pdf": 0.36,
}


def _extract_pdf_page_text(pdf_page, source_name: str) -> str:
    """Extract visible page text, separating the known fee-prospectus columns."""
    split_fraction = _TWO_COLUMN_PDF_SPLITS.get(source_name)
    if not hasattr(pdf_page, "width") or not hasattr(pdf_page, "height"):
        return pdf_page.extract_text() or ""

    if split_fraction is not None:
        split_x = pdf_page.width * split_fraction
        left = pdf_page.crop((0, 0, split_x, pdf_page.height)).extract_text() or ""
        right = pdf_page.crop((split_x, 0, pdf_page.width, pdf_page.height)).extract_text() or ""
        return "\n\n".join(column.strip() for column in (left, right) if column.strip())

    # Some PDFs contain duplicate or clipped text-layer characters outside the
    # visible page. pdfplumber.extract_text() includes them, which can attach a
    # visible clause to a heading that is only present off-page.
    visible_page = pdf_page.crop((0, 0, pdf_page.width, pdf_page.height))
    return visible_page.extract_text() or ""


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


def _structured_table_rows(pdf_page, source_name: str) -> list[str]:
    """Flatten bounded PDF table rows while preserving cell boundaries and headings."""
    rows: list[str] = []
    seen: set[str] = set()
    for table in pdf_page.extract_tables() or []:
        table_rows = table or []
        if table_rows and source_name == "prospectus-fee-information-2026.pdf":
            header = {" ".join(str(cell or "").split()).casefold()
                      for cell in (table_rows[0] or []) if cell}
            if {"description", "fee"}.issubset(header):
                rows.append("5. Miscellaneous Fees")
            elif {"timeline", "percentage of fee"}.issubset(header):
                rows.append("B. Fee Refund Policy")
        for row in table_rows:
            cells = [" ".join(str(cell).split()) for cell in (row or []) if cell]
            if len(cells) < 2:
                continue
            rendered = " | ".join(cells)
            # pdfplumber can identify a whole multi-column page as one giant table;
            # omit those pseudo-rows and keep actual row-shaped content.
            if len(rendered) > 600 or rendered in seen:
                continue
            seen.add(rendered)
            rows.append(f"Table row: {rendered}")
    return rows


def extract(
    path: str, doc_version: str, superseded: bool, failure_mode: str = "off"
) -> Document:
    """Return the document's text page by page.

    Detect pages with no text layer and OCR them unless `failure_mode="no_ocr"`;
    mark OCR-processed pages ocr=True.
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
                text = _extract_pdf_page_text(pdf_page, source.name)
                needs_ocr = not text.strip()
                table_rows = _structured_table_rows(pdf_page, source.name)
                ocr_used = False
                if needs_ocr and failure_mode != "no_ocr":
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
                        ocr_used = True
                    except Exception as exc:
                        raise RuntimeError(f"OCR failed on {source.name} page {number}: {exc}") from exc
                if table_rows:
                    text = f"{text.rstrip()}\n\n" + "\n".join(table_rows)
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
