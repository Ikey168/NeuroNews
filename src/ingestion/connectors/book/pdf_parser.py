"""
PDF parsing for books.

Extracts text and a chapter/section outline from a PDF.

Extraction chain (first that works):
  1. PyMuPDF (fitz)   — best quality; preserves bookmarks as chapter headings.
  2. pdfminer.six     — pure-Python fallback; text only, no bookmarks.
  3. OCR              — pytesseract + pdf2image for scanned/image-only PDFs.

Section detection:
  - If the PDF has a bookmark outline (fitz only), each bookmark becomes a
    BookSection node, preserving the part/chapter nesting.
  - Without bookmarks, heading lines are detected heuristically (all-caps or
    numbered "1.", "Chapter N") and used to split the text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from src.ingestion.connectors.book.models import BookSection


# Heuristic: a line is a heading if it is:
#   - short (≤ 80 chars), not a sentence (no terminal period mid-line)
#   - starts with "Chapter", "Part", "Section", a Roman numeral, or a number
_HEADING = re.compile(
    r"^\s*("
    r"(?:chapter|part|section|appendix|prologue|epilogue|introduction|conclusion)\b"
    r"|(?:[IVX]+\.?\s+\w)"       # Roman numerals
    r"|(?:\d{1,3}\.(?:\d+\.?)*\s+\w)"  # 1., 1.2., etc.
    r")",
    re.IGNORECASE,
)
_MIN_OCR_CHARS_PER_PAGE = 80  # below this → likely scanned, try OCR


@dataclass
class _Bookmark:
    title: str
    level: int  # 0 = top, 1 = sub, ...
    page: int


# --------------------------------------------------------------------------- #
# PyMuPDF path
# --------------------------------------------------------------------------- #

def _fitz_bookmarks(doc) -> List[_Bookmark]:
    toc = doc.get_toc(simple=False)
    return [_Bookmark(title=t, level=max(0, lvl - 1), page=pg) for lvl, t, pg, *_ in toc]


def _fitz_page_text(doc) -> List[str]:
    return [page.get_text() for page in doc]


def _assign_text_to_bookmarks(
    bookmarks: List[_Bookmark], page_texts: List[str]
) -> List[BookSection]:
    """Build a BookSection tree from bookmark entries + page text.

    Each bookmark owns the pages from its page to the next bookmark at the
    same or higher level.
    """
    if not bookmarks:
        return [BookSection(title="", text="\n".join(page_texts), level=0)]

    n_pages = len(page_texts)

    # Pair each bookmark with its text range.
    spans: List[Tuple[_Bookmark, str]] = []
    for i, bm in enumerate(bookmarks):
        start = min(bm.page, n_pages)
        end = n_pages
        for j in range(i + 1, len(bookmarks)):
            if bookmarks[j].level <= bm.level:
                end = min(bookmarks[j].page, n_pages)
                break
        text = "\n".join(page_texts[start:end]).strip()
        spans.append((bm, text))

    # Reconstruct the nesting.
    def _build(items: List[Tuple[_Bookmark, str]], parent_level: int) -> List[BookSection]:
        result: List[BookSection] = []
        i = 0
        while i < len(items):
            bm, text = items[i]
            if bm.level > parent_level:
                i += 1
                continue
            # Collect children (higher level number = deeper nesting)
            children_raw = []
            j = i + 1
            while j < len(items) and items[j][0].level > bm.level:
                children_raw.append(items[j])
                j += 1
            children = _build(children_raw, bm.level)
            result.append(BookSection(title=bm.title, text=text, level=bm.level, children=children))
            i = j if children_raw else i + 1
        return result

    top_level = spans[0][0].level if spans else 0
    return _build(spans, top_level - 1)


def _parse_with_fitz(pdf_bytes: bytes) -> Optional[tuple]:
    """Return (sections, extractor_tag) or None if fitz is unavailable."""
    try:
        import fitz  # PyMuPDF  # type: ignore
    except ImportError:
        return None

    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        page_texts = _fitz_page_text(doc)
        bookmarks = _fitz_bookmarks(doc)

    total_chars = sum(len(t) for t in page_texts)
    avg_per_page = total_chars / max(len(page_texts), 1)

    if avg_per_page < _MIN_OCR_CHARS_PER_PAGE:
        return None  # Scanned — let caller try OCR.

    if bookmarks:
        sections = _assign_text_to_bookmarks(bookmarks, page_texts)
    else:
        sections = _heuristic_sections("\n".join(page_texts))

    return (sections, "pymupdf")


# --------------------------------------------------------------------------- #
# pdfminer fallback
# --------------------------------------------------------------------------- #

def _parse_with_pdfminer(pdf_bytes: bytes) -> Optional[tuple]:
    try:
        from pdfminer.high_level import extract_text  # type: ignore
        import io as _io
    except ImportError:
        return None

    text = extract_text(_io.BytesIO(pdf_bytes))
    if not text or not text.strip():
        return None
    return (_heuristic_sections(text), "pdfminer")


# --------------------------------------------------------------------------- #
# OCR fallback
# --------------------------------------------------------------------------- #

def _parse_with_ocr(pdf_bytes: bytes) -> Optional[tuple]:
    """Convert PDF pages to images then OCR each one."""
    try:
        import pytesseract  # type: ignore
        from pdf2image import convert_from_bytes  # type: ignore
    except ImportError:
        return None

    images = convert_from_bytes(pdf_bytes)
    page_texts = [pytesseract.image_to_string(img) for img in images]
    text = "\n".join(page_texts)
    if not text.strip():
        return None
    return (_heuristic_sections(text), "ocr+tesseract")


# --------------------------------------------------------------------------- #
# Heading-based heuristic section split (no bookmark metadata)
# --------------------------------------------------------------------------- #

def _heuristic_sections(text: str) -> List[BookSection]:
    """Split text into sections at heading lines."""
    sections: List[BookSection] = []
    heading = ""
    buffer: List[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if stripped and len(stripped) <= 80 and _HEADING.match(stripped):
            if buffer and "".join(buffer).strip():
                sections.append(BookSection(title=heading, text="\n".join(buffer).strip(), level=1))
            heading = stripped
            buffer = []
        else:
            buffer.append(line)

    if buffer and "".join(buffer).strip():
        sections.append(BookSection(title=heading, text="\n".join(buffer).strip(), level=1))

    if not sections:
        sections = [BookSection(title="", text=text.strip(), level=0)]
    return sections


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def parse_pdf_sections(pdf_bytes: bytes) -> Tuple[List[BookSection], str]:
    """
    Extract sections from a PDF.

    Returns (sections, extractor) where extractor is one of:
    "pymupdf", "pdfminer", "ocr+tesseract", "none".
    """
    for attempt in (_parse_with_fitz, _parse_with_pdfminer, _parse_with_ocr):
        result = attempt(pdf_bytes)
        if result is not None:
            return result
    return ([], "none")
