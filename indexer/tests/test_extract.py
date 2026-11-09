from __future__ import annotations

import sys
from types import SimpleNamespace

from pipeline.extract import extract


class FakePage:
    def extract_text(self) -> str:
        return "Semester Freeze Fee Rs. 2,000"

    def extract_tables(self) -> list[list[list[str | None]]]:
        return [[
            ["Description", "Fee"],
            ["Semester Freeze Fee\n(within two weeks)", "Rs.", "2,000"],
            ["x" * 700, "whole-page pseudo table"],
        ]]


class FakePDF:
    pages = [FakePage()]

    def __enter__(self) -> FakePDF:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_pdf_extraction_preserves_table_cell_association(monkeypatch) -> None:
    source = "prospectus-fee-information-2026.pdf"
    monkeypatch.setitem(sys.modules, "pdfplumber", SimpleNamespace(open=lambda _: FakePDF()))

    document = extract(source, "2026", False)

    text = document.pages[0].text
    assert "Semester Freeze Fee Rs. 2,000" in text
    assert "5. Miscellaneous Fees\nTable row: Description | Fee" in text
    assert "Table row: Semester Freeze Fee (within two weeks) | Rs. | 2,000" in text
    assert "whole-page pseudo table" not in text


class FakeCrop:
    def __init__(self, text: str) -> None:
        self.text = text

    def extract_text(self) -> str:
        return self.text


class TwoColumnPage(FakePage):
    width = 612
    height = 792

    def extract_text(self) -> str:
        raise AssertionError("known two-column prospectus must use column crops")

    def crop(self, box: tuple[float, float, float, float]) -> FakeCrop:
        if box[2] < self.width:
            return FakeCrop(
                "3. Tuition Fee\nFor the academic year 2026-27 the\n"
                "tuition fee per credit hour applicable to all batches is as follows:\n"
                "Master and PhD Degree Programs\nTuition fee is Rs. 12,000 per credit hour."
            )
        return FakeCrop("5. Miscellaneous Fees\nDescription Fee\nIssuance of Certificate Fee Rs. 300")


def test_prospectus_columns_are_extracted_left_then_right(monkeypatch) -> None:
    source = "prospectus-fee-information-2026.pdf"
    pdf = FakePDF()
    pdf.pages = [TwoColumnPage()]
    monkeypatch.setitem(sys.modules, "pdfplumber", SimpleNamespace(open=lambda _: pdf))

    text = extract(source, "2026", False).pages[0].text

    assert text.index("tuition fee per credit hour") < text.index("5. Miscellaneous Fees")
    assert "tuition fee is rs. 12,000 per credit hour" in text.casefold()
    assert "Issuance of Certificate Fee Rs. 300" in text


class ClippedTextPage(FakePage):
    width = 420
    height = 595

    def extract_text(self) -> str:
        raise AssertionError("extract_text without page bounds includes hidden overflow")

    def crop(self, box: tuple[float, float, float, float]) -> FakeCrop:
        assert box == (0, 0, self.width, self.height)
        return FakeCrop("5.7 warning count is reset.\n5.8 Repeating a Course")


def test_pdf_text_is_clipped_to_visible_page_bounds(monkeypatch) -> None:
    pdf = FakePDF()
    pdf.pages = [ClippedTextPage()]
    monkeypatch.setitem(sys.modules, "pdfplumber", SimpleNamespace(open=lambda _: pdf))

    text = extract("academic-rules-handbook-2026.pdf", "2026", False).pages[0].text

    assert text.startswith("5.7 warning count is reset.")
    assert "5.8 Repeating a Course" in text
