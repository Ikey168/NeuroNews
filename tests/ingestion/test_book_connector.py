"""
Tests for the books connector (issue #521).

Covers:
- EPUB stdlib parsing (no ebooklib required)
- PDF section detection (no PyMuPDF required, using heuristic text split)
- BookConnector.parse() -> Document records with section_path metadata
- section_id / book_id stability
- book_metadata_to_documents: one Document per section with correct title/path
- Graceful empty: a book with no sections still emits a Document if it has text
- content_ref file:// URI construction
- registry: "book" is registered after importing the connectors package
"""

from __future__ import annotations

import io
import zipfile
from typing import List, Optional
from unittest.mock import patch

import pytest

from src.ingestion.connectors.book.connector import BookConnector, book_metadata_to_documents
from src.ingestion.connectors.book.epub_parser import _parse_epub_stdlib
from src.ingestion.connectors.book.models import BookMetadata, BookSection, book_id, section_id
from src.ingestion.connectors.book.pdf_parser import _heuristic_sections, parse_pdf_sections
from src.ingestion.connectors.base import RawDocument, SourceRef


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

def _make_epub(title: str = "Test Book", chapters: Optional[List[tuple]] = None) -> bytes:
    """Build a minimal but valid in-memory EPUB zip."""
    if chapters is None:
        chapters = [
            ("Chapter 1", "<html><body><p>Content of chapter one.</p></body></html>"),
            ("Chapter 2", "<html><body><p>Content of chapter two.</p></body></html>"),
        ]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", """\
<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>""")

        # OPF
        spine_items = "\n".join(
            f'<item id="ch{i}" href="ch{i}.xhtml" media-type="application/xhtml+xml"/>'
            for i in range(len(chapters))
        )
        spine_refs = "\n".join(
            f'<itemref idref="ch{i}"/>' for i in range(len(chapters))
        )
        opf = f"""\
<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"
            xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:title>{title}</dc:title>
    <dc:creator>Test Author</dc:creator>
    <dc:language>en</dc:language>
    <dc:identifier opf:scheme="ISBN">9780000000000</dc:identifier>
  </metadata>
  <manifest>
    {spine_items}
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
  </manifest>
  <spine toc="ncx">
    {spine_refs}
  </spine>
</package>"""
        zf.writestr("OEBPS/content.opf", opf)

        # NCX
        nav_points = "\n".join(
            f"""<navPoint id="np{i}" playOrder="{i+1}">
  <navLabel><text>{ch_title}</text></navLabel>
  <content src="ch{i}.xhtml"/>
</navPoint>"""
            for i, (ch_title, _) in enumerate(chapters)
        )
        ncx = f"""\
<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <navMap>
    {nav_points}
  </navMap>
</ncx>"""
        zf.writestr("OEBPS/toc.ncx", ncx)

        for i, (_, html) in enumerate(chapters):
            zf.writestr(f"OEBPS/ch{i}.xhtml", html)

    return buf.getvalue()


def _make_pdf_text() -> str:
    return (
        "Chapter 1 Introduction\n"
        + "This is the introduction of the book. " * 20 + "\n"
        + "Chapter 2 Background\n"
        + "Background material goes here. " * 20 + "\n"
        + "Chapter 3 Methods\n"
        + "Methods are described here. " * 20
    )


# --------------------------------------------------------------------------- #
# model tests
# --------------------------------------------------------------------------- #

class TestBookId:
    def test_isbn_preferred(self):
        assert book_id(isbn="9780000000000") == "isbn:9780000000000"

    def test_title_fallback(self):
        result = book_id(title="Some Book")
        assert result.startswith("book:")
        assert len(result) == len("book:") + 12

    def test_stable(self):
        assert book_id(title="Foo") == book_id(title="Foo")

    def test_different_titles_differ(self):
        assert book_id(title="A") != book_id(title="B")


class TestSectionId:
    def test_format(self):
        bid = book_id(isbn="9780000000000")
        sid = section_id(bid, ["Chapter 1", "Introduction"])
        assert sid.startswith(bid + "#")
        assert "chapter-1" in sid
        assert "introduction" in sid

    def test_empty_path(self):
        bid = book_id(isbn="0000")
        sid = section_id(bid, [])
        assert sid == bid + "#"


class TestBookSection:
    def test_all_sections_flat(self):
        s = BookSection(title="Ch 1", text="body", level=1)
        pairs = s.all_sections()
        assert len(pairs) == 1
        assert pairs[0][0] == ["Ch 1"]
        assert pairs[0][1] == "body"

    def test_all_sections_nested(self):
        s = BookSection(
            title="Part I",
            text="",
            level=0,
            children=[
                BookSection(title="Ch 1", text="chapter body", level=1),
                BookSection(title="Ch 2", text="chapter 2 body", level=1),
            ],
        )
        pairs = s.all_sections()
        assert len(pairs) == 2
        assert pairs[0][0] == ["Part I", "Ch 1"]
        assert pairs[1][0] == ["Part I", "Ch 2"]

    def test_skips_empty_body(self):
        s = BookSection(title="Empty", text="", level=0)
        assert s.all_sections() == []


# --------------------------------------------------------------------------- #
# EPUB parser tests (stdlib path)
# --------------------------------------------------------------------------- #

class TestEpubParser:
    def test_parse_title_and_authors(self):
        epub_bytes = _make_epub(title="My Book")
        meta = _parse_epub_stdlib(epub_bytes, file_path="/tmp/test.epub")
        assert meta.title == "My Book"
        assert "Test Author" in meta.authors
        assert meta.language == "en"
        assert meta.isbn == "9780000000000"
        assert meta.format == "epub"

    def test_parses_chapters_via_ncx(self):
        chapters = [
            ("Introduction", "<html><body><p>Intro text here.</p></body></html>"),
            ("Deep Dive", "<html><body><p>Deep text here.</p></body></html>"),
        ]
        meta = _parse_epub_stdlib(_make_epub(chapters=chapters), file_path="/tmp/t.epub")
        assert len(meta.sections) == 2
        assert meta.sections[0].title == "Introduction"
        assert "Intro text" in meta.sections[0].text
        assert meta.sections[1].title == "Deep Dive"

    def test_fallback_to_spine_without_ncx(self):
        # Build an EPUB without an NCX file, only OPF spine.
        chapters = [("Ch A", "<html><body><p>Content A.</p></body></html>")]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("mimetype", "application/epub+zip")
            zf.writestr("META-INF/container.xml", """\
<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="content.opf"
    media-type="application/oebps-package+xml"/></rootfiles>
</container>""")
            zf.writestr("content.opf", """\
<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Spine Only</dc:title><dc:language>en</dc:language>
  </metadata>
  <manifest>
    <item id="ch0" href="ch0.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="ch0"/></spine>
</package>""")
            zf.writestr("ch0.xhtml", "<html><body><p>Content A.</p></body></html>")
        meta = _parse_epub_stdlib(buf.getvalue(), file_path="/tmp/spine.epub")
        assert len(meta.sections) >= 1
        assert "Content A" in meta.sections[0].text

    def test_bad_zip_raises(self):
        with pytest.raises(ValueError, match="EPUB"):
            _parse_epub_stdlib(b"not a zip", file_path="/tmp/bad.epub")


# --------------------------------------------------------------------------- #
# PDF parser tests (heuristic path — no external deps)
# --------------------------------------------------------------------------- #

class TestPdfHeuristicSections:
    def test_splits_on_chapter_headings(self):
        text = _make_pdf_text()
        sections = _heuristic_sections(text)
        assert len(sections) == 3
        assert sections[0].title == "Chapter 1 Introduction"
        assert "introduction of the book" in sections[0].text
        assert sections[2].title == "Chapter 3 Methods"

    def test_no_headings_gives_one_section(self):
        text = "just some text without any headings at all"
        sections = _heuristic_sections(text)
        assert len(sections) == 1
        assert sections[0].title == ""

    def test_parse_pdf_sections_no_deps(self):
        # Without fitz/pdfminer/pytesseract, parse_pdf_sections returns "none".
        with (
            patch("src.ingestion.connectors.book.pdf_parser._parse_with_fitz", return_value=None),
            patch("src.ingestion.connectors.book.pdf_parser._parse_with_pdfminer", return_value=None),
            patch("src.ingestion.connectors.book.pdf_parser._parse_with_ocr", return_value=None),
        ):
            sections, extractor = parse_pdf_sections(b"%PDF-1.4")
            assert sections == []
            assert extractor == "none"


# --------------------------------------------------------------------------- #
# book_metadata_to_documents
# --------------------------------------------------------------------------- #

class TestBookMetadataToDocuments:
    def _simple_meta(self) -> BookMetadata:
        return BookMetadata(
            title="Test Book",
            authors=["Author A"],
            language="en",
            isbn="9780000000000",
            file_path="/books/test.epub",
            format="epub",
            sections=[
                BookSection(title="Chapter 1", text="Chapter one text.", level=1),
                BookSection(title="Chapter 2", text="Chapter two text.", level=1),
            ],
            extractor="stdlib",
        )

    def test_one_doc_per_section(self):
        meta = self._simple_meta()
        docs = book_metadata_to_documents(meta, ingested_at=1000000)
        assert len(docs) == 2

    def test_source_type(self):
        docs = book_metadata_to_documents(self._simple_meta(), ingested_at=1)
        assert all(d.source_type == "book" for d in docs)

    def test_section_path_in_metadata(self):
        docs = book_metadata_to_documents(self._simple_meta(), ingested_at=1)
        assert docs[0].metadata["section_path"] == ["Chapter 1"]
        assert docs[1].metadata["section_path"] == ["Chapter 2"]

    def test_book_title_in_metadata(self):
        docs = book_metadata_to_documents(self._simple_meta(), ingested_at=1)
        assert all(d.metadata["book_title"] == "Test Book" for d in docs)

    def test_content_ref_uri(self):
        docs = book_metadata_to_documents(self._simple_meta(), ingested_at=1)
        assert docs[0].content_ref.startswith("file://")
        assert "chapter-1" in docs[0].content_ref

    def test_title_includes_section(self):
        docs = book_metadata_to_documents(self._simple_meta(), ingested_at=1)
        assert "Chapter 1" in docs[0].title
        assert "Test Book" in docs[0].title

    def test_nested_sections(self):
        meta = BookMetadata(
            title="Nested",
            language="en",
            file_path="/tmp/n.epub",
            format="epub",
            sections=[
                BookSection(
                    title="Part I",
                    text="",
                    level=0,
                    children=[
                        BookSection(title="Ch 1", text="Ch 1 text.", level=1),
                        BookSection(title="Ch 2", text="Ch 2 text.", level=1),
                    ],
                )
            ],
            extractor="stdlib",
        )
        docs = book_metadata_to_documents(meta, ingested_at=1)
        assert len(docs) == 2
        assert docs[0].metadata["section_path"] == ["Part I", "Ch 1"]
        assert docs[1].metadata["section_path"] == ["Part I", "Ch 2"]

    def test_no_sections_fallback(self):
        meta = BookMetadata(
            title="Empty",
            language="en",
            file_path="/tmp/e.epub",
            format="epub",
            sections=[BookSection(title="", text="All the text.", level=0)],
            extractor="none",
        )
        docs = book_metadata_to_documents(meta, ingested_at=1)
        assert len(docs) == 1
        assert "All the text" in docs[0].content

    def test_isbn_in_metadata(self):
        meta = self._simple_meta()
        docs = book_metadata_to_documents(meta, ingested_at=1)
        assert docs[0].metadata["isbn"] == "9780000000000"

    def test_language_propagated(self):
        meta = self._simple_meta()
        meta.language = "fr"
        docs = book_metadata_to_documents(meta, ingested_at=1)
        assert all(d.language == "fr" for d in docs)


# --------------------------------------------------------------------------- #
# BookConnector integration
# --------------------------------------------------------------------------- #

class TestBookConnector:
    def test_source_type(self):
        assert BookConnector.source_type == "book"

    def test_discover_yields_srefs(self):
        connector = BookConnector()
        refs = list(connector.discover(["/books/a.epub", "/books/b.pdf"]))
        assert len(refs) == 2
        assert refs[0].metadata["format"] == "epub"
        assert refs[1].metadata["format"] == "pdf"

    def test_discover_none_yields_nothing(self):
        connector = BookConnector()
        assert list(connector.discover(None)) == []

    def test_fetch_missing_file(self):
        connector = BookConnector()
        ref = SourceRef(locator="/nonexistent/book.epub")
        with pytest.raises(FileNotFoundError):
            connector.fetch(ref)

    def test_parse_epub(self, tmp_path):
        epub_bytes = _make_epub(title="Parse Me", chapters=[
            ("Ch 1", "<html><body><p>First chapter.</p></body></html>"),
            ("Ch 2", "<html><body><p>Second chapter.</p></body></html>"),
        ])
        epub_file = tmp_path / "parse_me.epub"
        epub_file.write_bytes(epub_bytes)

        connector = BookConnector()
        ref = SourceRef(locator=str(epub_file), title="parse_me", metadata={"format": "epub"})
        raw = connector.fetch(ref)
        docs = connector.parse(raw)

        assert len(docs) == 2
        assert all(d.source_type == "book" for d in docs)
        titles = [d.title for d in docs]
        assert any("Ch 1" in t for t in titles)
        assert any("Ch 2" in t for t in titles)

    def test_parse_pdf_heuristic(self, tmp_path):
        # Mock fitz/pdfminer/OCR away; provide a fake bytes + heuristic text via patching.
        fake_text = (
            "Chapter 1 First\n" + "First chapter content. " * 15 + "\n"
            "Chapter 2 Second\n" + "Second chapter content. " * 15
        )
        pdf_file = tmp_path / "book.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")

        def fake_fitz(pdf_bytes):
            from src.ingestion.connectors.book.pdf_parser import _heuristic_sections
            return (_heuristic_sections(fake_text), "pymupdf")

        connector = BookConnector()
        ref = SourceRef(locator=str(pdf_file), title="book", metadata={"format": "pdf"})

        with patch("src.ingestion.connectors.book.pdf_parser._parse_with_fitz", side_effect=fake_fitz):
            raw = connector.fetch(ref)
            docs = connector.parse(raw)

        assert len(docs) == 2
        assert docs[0].metadata["section_path"] == ["Chapter 1 First"]
        assert docs[1].metadata["section_path"] == ["Chapter 2 Second"]
        assert docs[0].metadata["extractor"] == "pymupdf"

    def test_unsupported_format(self):
        connector = BookConnector()
        raw = RawDocument(
            ref=SourceRef(locator="/tmp/x.docx"),
            content=b"data",
            content_type="application/msword",
        )
        with pytest.raises(ValueError, match="Unsupported"):
            connector.parse(raw)

    def test_harvest_skips_missing_files(self):
        connector = BookConnector()
        docs = list(connector.harvest(["/no/such/file.epub"]))
        assert docs == []

    def test_registered_in_registry(self):
        import src.ingestion.connectors  # noqa: F401 — triggers registration
        from src.ingestion.connectors.registry import is_registered
        assert is_registered("book")
