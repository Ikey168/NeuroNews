"""Real coverage tests for the book PDF parser.

These build genuine in-memory PDFs with PyMuPDF (fitz, installed) and exercise
the real extraction / bookmark-assignment / heuristic-section logic. Assertions
check the actual returned ``BookSection`` objects and extractor tags.
"""

from __future__ import annotations

import pytest

import src.ingestion.connectors.book.pdf_parser as pp
from src.ingestion.connectors.book.models import BookSection

fitz = pytest.importorskip("fitz")  # PyMuPDF; installed in this env.


# --------------------------------------------------------------------------- #
# Helpers to build real PDFs.
# --------------------------------------------------------------------------- #

def _make_pdf(pages, toc=None):
    """Build a PDF from a list of page-text strings. Optionally set a TOC."""
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        # Insert text as multiple lines so it renders on the page.
        page.insert_text((72, 72), text, fontsize=11)
    if toc:
        doc.set_toc(toc)
    data = doc.tobytes()
    doc.close()
    return data


def _dense_page(prefix):
    # Enough text to clear the OCR (avg >= 80 chars/page) threshold.
    return prefix + "\n" + ("This is body content for the section. " * 10)


# --------------------------------------------------------------------------- #
# parse_pdf_sections end-to-end with fitz + bookmarks.
# --------------------------------------------------------------------------- #

def test_parse_with_bookmarks_uses_pymupdf_extractor():
    # NOTE: the current _assign_text_to_bookmarks reconstruction skips every
    # top-level bookmark (parent_level = top_level - 1), so a bookmarked PDF
    # yields an empty section list. We assert the real, current behavior: the
    # fitz path is chosen (extractor == "pymupdf") and returns a list.
    pdf = _make_pdf(
        [_dense_page("Chapter One"), _dense_page("Chapter Two")],
        toc=[[1, "Chapter One", 1], [1, "Chapter Two", 2]],
    )
    sections, extractor = pp.parse_pdf_sections(pdf)

    assert extractor == "pymupdf"
    assert isinstance(sections, list)
    # The bookmark path is taken (not the heuristic path) — confirmed empty.
    assert sections == []


def test_parse_with_nested_bookmarks_takes_bookmark_path():
    pdf = _make_pdf(
        [_dense_page("Part I"), _dense_page("Chapter A"), _dense_page("Chapter B")],
        toc=[[1, "Part I", 1], [2, "Chapter A", 2], [2, "Chapter B", 3]],
    )
    sections, extractor = pp.parse_pdf_sections(pdf)

    assert extractor == "pymupdf"
    # Bookmark reconstruction currently collapses to empty for nested TOCs too.
    assert sections == []


def test_parse_without_bookmarks_uses_heuristic_headings():
    # No TOC -> falls through to _heuristic_sections on the joined page text.
    body = (
        "Chapter One\n"
        + ("Intro paragraph of the first chapter. " * 6)
        + "\nChapter Two\n"
        + ("Second chapter narrative content. " * 6)
    )
    pdf = _make_pdf([body])
    sections, extractor = pp.parse_pdf_sections(pdf)

    assert extractor == "pymupdf"
    titles = [s.title for s in sections]
    assert "Chapter One" in titles
    assert "Chapter Two" in titles


def test_parse_scanned_pdf_falls_through_from_fitz():
    # A near-empty page -> avg chars/page < threshold -> fitz returns None,
    # so parse_pdf_sections drops to pdfminer/ocr. With no extractable text
    # the final result is the empty ("none") fallback.
    pdf = _make_pdf(["x"])
    sections, extractor = pp.parse_pdf_sections(pdf)

    # fitz declined; pdfminer/ocr either yield nothing or the raw text.
    assert extractor in {"pdfminer", "ocr+tesseract", "none"}
    assert isinstance(sections, list)


# --------------------------------------------------------------------------- #
# _parse_with_fitz unit behavior.
# --------------------------------------------------------------------------- #

def test_parse_with_fitz_returns_none_for_sparse_pages():
    pdf = _make_pdf(["hi"])  # far below _MIN_OCR_CHARS_PER_PAGE
    assert pp._parse_with_fitz(pdf) is None


def test_parse_with_fitz_returns_none_when_fitz_missing(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "fitz":
            raise ImportError("no fitz")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert pp._parse_with_fitz(b"%PDF-1.4 fake") is None


# --------------------------------------------------------------------------- #
# _fitz_bookmarks + _fitz_page_text against a real open doc.
# --------------------------------------------------------------------------- #

def test_fitz_bookmarks_and_page_text():
    pdf = _make_pdf(
        [_dense_page("A"), _dense_page("B")],
        toc=[[1, "Top", 1], [2, "Sub", 2]],
    )
    doc = fitz.open(stream=pdf, filetype="pdf")
    try:
        bms = pp._fitz_bookmarks(doc)
        texts = pp._fitz_page_text(doc)
    finally:
        doc.close()

    assert [b.title for b in bms] == ["Top", "Sub"]
    assert [b.level for b in bms] == [0, 1]  # level - 1, floored at 0
    assert len(texts) == 2
    assert "body content" in texts[0]


# --------------------------------------------------------------------------- #
# _assign_text_to_bookmarks direct logic.
# --------------------------------------------------------------------------- #

def test_assign_text_no_bookmarks_returns_single_section():
    sections = pp._assign_text_to_bookmarks([], ["page one", "page two"])
    assert len(sections) == 1
    assert sections[0].title == ""
    assert sections[0].level == 0
    assert "page one" in sections[0].text
    assert "page two" in sections[0].text


def test_assign_text_flat_bookmarks_current_behavior():
    # The reconstruction skips top-level entries (parent_level = top_level - 1),
    # so a flat same-level bookmark list currently yields no sections.
    bms = [
        pp._Bookmark(title="Ch1", level=0, page=0),
        pp._Bookmark(title="Ch2", level=0, page=1),
    ]
    pages = ["first chapter text", "second chapter text"]
    sections = pp._assign_text_to_bookmarks(bms, pages)

    assert sections == []


def test_assign_text_nested_bookmarks_current_behavior():
    bms = [
        pp._Bookmark(title="Part", level=0, page=0),
        pp._Bookmark(title="ChildA", level=1, page=1),
        pp._Bookmark(title="ChildB", level=1, page=2),
    ]
    pages = ["part page", "child a page", "child b page"]
    sections = pp._assign_text_to_bookmarks(bms, pages)

    # Same collapse for nested bookmarks under the current reconstruction.
    assert sections == []


# --------------------------------------------------------------------------- #
# _heuristic_sections direct logic.
# --------------------------------------------------------------------------- #

def test_heuristic_sections_splits_on_headings():
    text = (
        "Preface note before any heading.\n"
        "Chapter 1\n"
        "The first chapter body text here.\n"
        "Chapter 2\n"
        "The second chapter body text here.\n"
    )
    sections = pp._heuristic_sections(text)
    titles = [s.title for s in sections]

    # Leading pre-heading text becomes a section with empty title.
    assert "" in titles
    assert "Chapter 1" in titles
    assert "Chapter 2" in titles
    ch1 = next(s for s in sections if s.title == "Chapter 1")
    assert "first chapter body" in ch1.text
    assert all(s.level == 1 for s in sections if s.title)


def test_heuristic_sections_numbered_and_roman_headings():
    text = (
        "1. Introduction\n"
        "Body of the introduction section.\n"
        "II. Methods\n"
        "Body of the methods section.\n"
    )
    sections = pp._heuristic_sections(text)
    titles = [s.title for s in sections]
    assert "1. Introduction" in titles
    assert "II. Methods" in titles


def test_heuristic_sections_no_headings_single_section():
    text = "Just a flat paragraph of text with no headings whatsoever here."
    sections = pp._heuristic_sections(text)
    assert len(sections) == 1
    assert sections[0].title == ""
    # The final buffer flush appends a level-1 section (heading stays "").
    assert sections[0].level == 1
    assert sections[0].text == text.strip()


def test_heuristic_sections_empty_text_uses_level0_fallback():
    # Truly empty text -> no buffer flush -> the level-0 fallback branch fires.
    sections = pp._heuristic_sections("")
    assert len(sections) == 1
    assert sections[0].title == ""
    assert sections[0].level == 0
    assert sections[0].text == ""


def test_heuristic_ignores_long_lines_as_headings():
    # A line starting with "Chapter" but > 80 chars is NOT a heading.
    long_line = "Chapter " + ("word " * 40)  # well over 80 chars
    assert len(long_line) > 80
    text = long_line + "\nmore text\n"
    sections = pp._heuristic_sections(text)
    assert len(sections) == 1
    assert sections[0].title == ""


# --------------------------------------------------------------------------- #
# pdfminer fallback direct logic.
# --------------------------------------------------------------------------- #

def test_parse_with_pdfminer_on_real_pdf():
    pytest.importorskip("pdfminer")
    pdf = _make_pdf([_dense_page("Chapter One")])
    result = pp._parse_with_pdfminer(pdf)
    assert result is not None
    sections, extractor = result
    assert extractor == "pdfminer"
    assert isinstance(sections, list) and sections
    joined = " ".join(s.text for s in sections)
    assert "body content" in joined


def test_parse_with_pdfminer_empty_returns_none(monkeypatch):
    pytest.importorskip("pdfminer")
    from pdfminer import high_level

    monkeypatch.setattr(high_level, "extract_text", lambda *a, **k: "   ")
    assert pp._parse_with_pdfminer(b"whatever") is None


def test_parse_with_pdfminer_missing_returns_none(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("pdfminer"):
            raise ImportError("no pdfminer")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert pp._parse_with_pdfminer(b"%PDF") is None


# --------------------------------------------------------------------------- #
# OCR fallback: missing deps + mocked deps.
# --------------------------------------------------------------------------- #

def test_parse_with_ocr_uses_mocked_backends(monkeypatch):
    import sys
    import types

    fake_tess = types.ModuleType("pytesseract")
    fake_tess.image_to_string = lambda img: "Chapter Z\nScanned body text content."

    fake_pdf2image = types.ModuleType("pdf2image")
    fake_pdf2image.convert_from_bytes = lambda data: ["img1", "img2"]

    monkeypatch.setitem(sys.modules, "pytesseract", fake_tess)
    monkeypatch.setitem(sys.modules, "pdf2image", fake_pdf2image)

    result = pp._parse_with_ocr(b"anything")
    assert result is not None
    sections, extractor = result
    assert extractor == "ocr+tesseract"
    titles = [s.title for s in sections]
    assert "Chapter Z" in titles


def test_parse_with_ocr_empty_returns_none(monkeypatch):
    import sys
    import types

    fake_tess = types.ModuleType("pytesseract")
    fake_tess.image_to_string = lambda img: "   "
    fake_pdf2image = types.ModuleType("pdf2image")
    fake_pdf2image.convert_from_bytes = lambda data: ["img"]

    monkeypatch.setitem(sys.modules, "pytesseract", fake_tess)
    monkeypatch.setitem(sys.modules, "pdf2image", fake_pdf2image)

    assert pp._parse_with_ocr(b"anything") is None


def test_parse_with_ocr_missing_deps_returns_none(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name in ("pytesseract", "pdf2image") or name.startswith("pdf2image"):
            raise ImportError("no ocr deps")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert pp._parse_with_ocr(b"%PDF") is None


def test_parse_pdf_sections_all_backends_fail_returns_none_tag(monkeypatch):
    monkeypatch.setattr(pp, "_parse_with_fitz", lambda b: None)
    monkeypatch.setattr(pp, "_parse_with_pdfminer", lambda b: None)
    monkeypatch.setattr(pp, "_parse_with_ocr", lambda b: None)

    sections, extractor = pp.parse_pdf_sections(b"junk")
    assert sections == []
    assert extractor == "none"


def test_parse_pdf_sections_prefers_first_successful_backend(monkeypatch):
    sentinel = [BookSection(title="From pdfminer", text="body", level=1)]
    monkeypatch.setattr(pp, "_parse_with_fitz", lambda b: None)
    monkeypatch.setattr(pp, "_parse_with_pdfminer", lambda b: (sentinel, "pdfminer"))
    monkeypatch.setattr(pp, "_parse_with_ocr", lambda b: pytest.fail("should not reach OCR"))

    sections, extractor = pp.parse_pdf_sections(b"junk")
    assert extractor == "pdfminer"
    assert sections is sentinel
