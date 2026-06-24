"""
PDF parsing for papers.

Best-effort extraction of plain text and a section outline from a paper PDF.
Text extraction uses PyMuPDF (``fitz``) when installed and degrades gracefully
when it is not. The reference list for the citation graph is sourced from the
metadata API (see ``references.py``), not from PDF parsing; GROBID can be slotted
in here later for higher-fidelity structure extraction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

# Common top-level section headings found in academic papers.
_HEADING = re.compile(
    r"^\s*(?:\d+\.?\s+)?("
    r"abstract|introduction|background|related work|methods?|methodology|"
    r"approach|experiments?|results?|evaluation|discussion|conclusions?|"
    r"references|acknowledge?ments?|appendix"
    r")\s*$",
    re.IGNORECASE,
)


@dataclass
class Section:
    heading: str
    body: str


@dataclass
class ParsedPdf:
    text: str = ""
    sections: List[Section] = field(default_factory=list)
    extractor: str = "none"


def split_sections(text: str) -> List[Section]:
    """Split paper text into sections by recognized headings.

    Pure and dependency-free, so it is testable without a PDF backend. Text
    before the first recognized heading is captured under a ``preamble`` section.
    """
    sections: List[Section] = []
    heading = "preamble"
    buffer: List[str] = []

    for line in text.splitlines():
        match = _HEADING.match(line)
        if match:
            if buffer and any(b.strip() for b in buffer):
                sections.append(Section(heading=heading, body="\n".join(buffer).strip()))
            heading = match.group(1).strip().lower()
            buffer = []
        else:
            buffer.append(line)

    if buffer and any(b.strip() for b in buffer):
        sections.append(Section(heading=heading, body="\n".join(buffer).strip()))
    return sections


def extract_pdf_text(pdf_bytes: bytes) -> Optional[str]:
    """Extract plain text from PDF bytes using PyMuPDF, or None if unavailable."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return None
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        return "\n".join(page.get_text() for page in doc)


def parse_pdf(pdf_bytes: bytes) -> ParsedPdf:
    """Parse PDF bytes into text plus a best-effort section outline."""
    text = extract_pdf_text(pdf_bytes)
    if text is None:
        return ParsedPdf(extractor="none")
    return ParsedPdf(text=text, sections=split_sections(text), extractor="pymupdf")
