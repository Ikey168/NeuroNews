"""
Tests for the upload connector (issue #524).

Covers:
- Format detection: extension → magic bytes → heuristic
- Text extraction: markdown, html, email, text (all stdlib/available libs)
- PDF/DOCX paths covered via mocking (no binary fixtures needed)
- UploadConnector: discover (files + paste), fetch, parse, harvest
- Document output: source_type="note", stable IDs, metadata, title extraction
- Error paths: missing file, unsupported extension, empty content
- Registry: "note" registered after import
"""

from __future__ import annotations

import io
import zipfile
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from unittest.mock import patch

import pytest

from src.ingestion.connectors.base import SourceRef
from src.ingestion.connectors.upload.connector import UploadConnector, _stable_id
from src.ingestion.connectors.upload.detectors import detect_encoding, detect_format
from src.ingestion.connectors.upload.parsers import extract_text


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

_MD = b"# Hello World\n\nThis is a **markdown** document.\n\n## Section 2\n\nMore content."
_HTML = b"""<!DOCTYPE html><html><head><title>Test Page</title></head>
<body><h1>Heading</h1><p>Some paragraph text here.</p><script>alert(1)</script></body></html>"""
_TEXT = b"Plain text content.\nLine two.\nLine three."
_EMAIL_PLAIN = (
    b"From: Alice <alice@example.com>\r\n"
    b"To: Bob <bob@example.com>\r\n"
    b"Subject: Meeting notes\r\n"
    b"Date: Thu, 01 Jan 2026 10:00:00 +0000\r\n"
    b"MIME-Version: 1.0\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n"
    b"\r\n"
    b"Here are the meeting notes.\nAction item: do the thing."
)


def _make_multipart_email() -> bytes:
    msg = MIMEMultipart("alternative")
    msg["From"] = "sender@example.com"
    msg["To"] = "receiver@example.com"
    msg["Subject"] = "Multipart Email"
    msg["Date"] = "Thu, 01 Jan 2026 12:00:00 +0000"
    msg.attach(MIMEText("Plain text body.", "plain", "utf-8"))
    msg.attach(MIMEText("<p>HTML body.</p>", "html", "utf-8"))
    return msg.as_bytes()


def _make_docx_bytes(text: str = "Hello from DOCX") -> bytes:
    """Minimal DOCX (ZIP) with word/document.xml containing the given text."""
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f'<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", xml)
        zf.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# detect_format
# --------------------------------------------------------------------------- #

class TestDetectFormat:
    def test_extension_md(self):
        assert detect_format(b"# Hello", "note.md") == "markdown"

    def test_extension_markdown(self):
        assert detect_format(b"text", "doc.markdown") == "markdown"

    def test_extension_pdf(self):
        assert detect_format(b"%PDF-1.4 ...", "file.pdf") == "pdf"

    def test_extension_html(self):
        assert detect_format(b"<html>", "page.html") == "html"

    def test_extension_eml(self):
        assert detect_format(b"From: x", "msg.eml") == "email"

    def test_extension_txt(self):
        assert detect_format(b"text", "note.txt") == "text"

    def test_extension_docx(self):
        assert detect_format(b"PK\x03\x04", "doc.docx") == "docx"

    def test_magic_pdf_bytes(self):
        assert detect_format(b"%PDF-1.4 content", "") == "pdf"

    def test_magic_docx_bytes(self):
        assert detect_format(b"PK\x03\x04extra", "") == "docx"

    def test_magic_email_from(self):
        assert detect_format(b"From alice@example.com Thu ...", "") == "email"

    def test_magic_html_doctype(self):
        assert detect_format(b"<!DOCTYPE html><html>", "") == "html"

    def test_heuristic_markdown_heading(self):
        assert detect_format(b"# Title\n\nContent", "") == "markdown"

    def test_heuristic_plain_text(self):
        assert detect_format(b"Just plain text here.", "") == "text"

    def test_rst_treated_as_markdown(self):
        assert detect_format(b"title", "doc.rst") == "markdown"


class TestDetectEncoding:
    def test_utf8(self):
        enc = detect_encoding("hello world".encode("utf-8"))
        assert "utf" in enc or enc == "ascii"

    def test_latin1(self):
        enc = detect_encoding("caf\xe9".encode("latin-1"))
        # chardet should detect something reasonable
        assert enc  # non-empty


# --------------------------------------------------------------------------- #
# extract_text parsers
# --------------------------------------------------------------------------- #

class TestExtractText:
    def test_markdown_extracts_text(self):
        text, meta = extract_text(_MD, "markdown")
        assert "Hello World" in text
        assert "markdown" in text.lower() or "More content" in text
        assert meta["original_format"] == "markdown"

    def test_markdown_extracts_title(self):
        _, meta = extract_text(_MD, "markdown")
        assert meta.get("title") == "Hello World"

    def test_html_extracts_text(self):
        text, _ = extract_text(_HTML, "html")
        assert "Heading" in text
        assert "paragraph text" in text
        # Script content should be stripped.
        assert "alert" not in text

    def test_html_extracts_title(self):
        _, meta = extract_text(_HTML, "html")
        assert meta.get("title") == "Test Page"

    def test_plain_text(self):
        text, meta = extract_text(_TEXT, "text")
        assert "Plain text content" in text
        assert meta["extractor"] == "raw"

    def test_email_plain_extracts_body(self):
        text, meta = extract_text(_EMAIL_PLAIN, "email")
        assert "meeting notes" in text.lower()
        assert meta["subject"] == "Meeting notes"
        assert "alice@example.com" in meta["from"]

    def test_email_multipart_prefers_plain(self):
        eml = _make_multipart_email()
        text, meta = extract_text(eml, "email")
        assert "Plain text body" in text
        assert meta["subject"] == "Multipart Email"

    def test_docx_stdlib_fallback(self):
        docx_bytes = _make_docx_bytes("DOCX content here")
        text, meta = extract_text(docx_bytes, "docx")
        assert "DOCX content here" in text
        assert meta["extractor"] in ("python-docx", "stdlib-xml")

    def test_pdf_no_backend_returns_empty(self):
        with (
            patch("src.ingestion.connectors.upload.parsers._parse_pdf",
                  return_value=("", {"extractor": "none"})),
        ):
            _, meta = extract_text(b"%PDF-1.4", "pdf")
            assert meta["extractor"] == "none"

    def test_unknown_format_falls_back_to_text(self):
        text, meta = extract_text(b"some bytes", "unknown_format")
        # Should not raise; extractor may be "raw" or "error"
        assert isinstance(text, str)
        assert isinstance(meta, dict)

    def test_parser_error_returns_empty_not_raises(self):
        # Corrupt docx bytes (not a valid zip).
        text, _ = extract_text(b"not a zip file at all", "docx")
        assert isinstance(text, str)


# --------------------------------------------------------------------------- #
# UploadConnector
# --------------------------------------------------------------------------- #

class TestUploadConnector:
    def test_source_type(self):
        assert UploadConnector.source_type == "note"

    # --- discover ---------------------------------------------------------- #

    def test_discover_file_path(self, tmp_path):
        f = tmp_path / "note.md"
        f.write_bytes(_MD)
        c = UploadConnector()
        refs = list(c.discover([str(f)]))
        assert len(refs) == 1
        assert refs[0].locator == str(f.resolve())
        assert refs[0].metadata["format"] == "md"

    def test_discover_path_object(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_bytes(_TEXT)
        c = UploadConnector()
        refs = list(c.discover([f]))
        assert refs[0].locator == str(f.resolve())

    def test_discover_paste(self):
        c = UploadConnector()
        refs = list(c.discover([{"paste": "# Quick note", "title": "My Note"}]))
        assert len(refs) == 1
        assert refs[0].locator.startswith("paste://")
        assert refs[0].title == "My Note"
        assert refs[0].metadata["paste"] is True

    def test_discover_paste_markdown_detected(self):
        c = UploadConnector()
        refs = list(c.discover([{"paste": "# Heading\nContent"}]))
        assert refs[0].metadata["format"] == "markdown"

    def test_discover_paste_text_detected(self):
        c = UploadConnector()
        refs = list(c.discover([{"paste": "Plain prose with no markdown."}]))
        assert refs[0].metadata["format"] == "text"

    def test_discover_mixed_query(self, tmp_path):
        f = tmp_path / "doc.md"
        f.write_bytes(_MD)
        c = UploadConnector()
        refs = list(c.discover([str(f), {"paste": "note text", "title": "Quick"}]))
        assert len(refs) == 2
        assert refs[1].metadata["paste"] is True

    def test_discover_none_yields_nothing(self):
        c = UploadConnector()
        assert list(c.discover(None)) == []

    def test_discover_single_string(self, tmp_path):
        f = tmp_path / "x.txt"
        f.write_bytes(_TEXT)
        c = UploadConnector()
        refs = list(c.discover(str(f)))
        assert len(refs) == 1

    # --- fetch ------------------------------------------------------------- #

    def test_fetch_file(self, tmp_path):
        f = tmp_path / "note.md"
        f.write_bytes(_MD)
        c = UploadConnector()
        ref = SourceRef(locator=str(f), title="note", metadata={"format": "md"})
        raw = c.fetch(ref)
        assert raw.content == _MD

    def test_fetch_paste(self):
        c = UploadConnector()
        ref = c._paste_ref({"paste": "Hello world", "title": "T"})
        raw = c.fetch(ref)
        assert raw.content == b"Hello world"

    def test_fetch_missing_file(self):
        c = UploadConnector()
        ref = SourceRef(locator="/no/such/file.md")
        with pytest.raises(FileNotFoundError):
            c.fetch(ref)

    def test_fetch_unsupported_extension(self, tmp_path):
        f = tmp_path / "binary.exe"
        f.write_bytes(b"\x00\x01")
        c = UploadConnector()
        ref = SourceRef(locator=str(f))
        with pytest.raises(ValueError, match="Unsupported"):
            c.fetch(ref)

    # --- parse ------------------------------------------------------------- #

    def test_parse_markdown_file(self, tmp_path):
        f = tmp_path / "note.md"
        f.write_bytes(_MD)
        c = UploadConnector()
        ref = SourceRef(locator=str(f), title="note", metadata={"format": "md"})
        raw = c.fetch(ref)
        docs = c.parse(raw)
        assert len(docs) == 1
        assert docs[0].source_type == "note"
        assert "Hello World" in (docs[0].title or "")
        assert docs[0].metadata["format"] == "markdown"

    def test_parse_html(self, tmp_path):
        f = tmp_path / "page.html"
        f.write_bytes(_HTML)
        c = UploadConnector()
        ref = SourceRef(locator=str(f), title="page", metadata={"format": "html"})
        raw = c.fetch(ref)
        docs = c.parse(raw)
        assert docs[0].title == "Test Page"
        assert docs[0].metadata["format"] == "html"

    def test_parse_email(self, tmp_path):
        f = tmp_path / "msg.eml"
        f.write_bytes(_EMAIL_PLAIN)
        c = UploadConnector()
        ref = SourceRef(locator=str(f), title="msg", metadata={"format": "eml"})
        raw = c.fetch(ref)
        docs = c.parse(raw)
        assert docs[0].title == "Meeting notes"
        assert "Meeting notes" in docs[0].metadata["subject"]

    def test_parse_plain_text(self, tmp_path):
        f = tmp_path / "note.txt"
        f.write_bytes(_TEXT)
        c = UploadConnector()
        ref = SourceRef(locator=str(f), title="note", metadata={"format": "txt"})
        raw = c.fetch(ref)
        docs = c.parse(raw)
        assert "Plain text content" in docs[0].content

    def test_parse_paste(self):
        c = UploadConnector()
        ref = c._paste_ref({"paste": "# My Note\nImportant thought.", "title": "My Note"})
        raw = c.fetch(ref)
        docs = c.parse(raw)
        assert docs[0].source_type == "note"
        assert docs[0].content_ref.startswith("paste://")
        assert docs[0].url is None

    def test_parse_empty_content_returns_no_docs(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_bytes(b"   ")
        c = UploadConnector()
        ref = SourceRef(locator=str(f), title="empty", metadata={"format": "txt"})
        raw = c.fetch(ref)
        docs = c.parse(raw)
        assert docs == []

    def test_parse_content_ref_is_file_uri(self, tmp_path):
        f = tmp_path / "doc.md"
        f.write_bytes(_MD)
        c = UploadConnector()
        ref = SourceRef(locator=str(f), title="doc", metadata={"format": "md"})
        raw = c.fetch(ref)
        docs = c.parse(raw)
        assert docs[0].content_ref.startswith("file://")

    def test_parse_stable_document_id(self, tmp_path):
        f = tmp_path / "note.md"
        f.write_bytes(_MD)
        c = UploadConnector()
        ref = SourceRef(locator=str(f), title="note", metadata={"format": "md"})

        raw1 = c.fetch(ref)
        raw2 = c.fetch(ref)
        docs1 = c.parse(raw1)
        docs2 = c.parse(raw2)
        assert docs1[0].document_id == docs2[0].document_id

    def test_parse_language_default(self, tmp_path):
        f = tmp_path / "note.txt"
        f.write_bytes(_TEXT)
        c = UploadConnector(default_language="fr")
        ref = SourceRef(locator=str(f), title="note", metadata={"format": "txt"})
        raw = c.fetch(ref)
        docs = c.parse(raw)
        assert docs[0].language == "fr"

    def test_parse_paste_language_override(self):
        c = UploadConnector()
        ref = c._paste_ref({"paste": "Bonjour monde", "title": "FR", "language": "fr"})
        raw = c.fetch(ref)
        docs = c.parse(raw)
        assert docs[0].language == "fr"

    # --- harvest ----------------------------------------------------------- #

    def test_harvest_skips_missing_files(self):
        c = UploadConnector()
        docs = list(c.harvest(["/no/such/file.md"]))
        assert docs == []

    def test_harvest_multiple_files(self, tmp_path):
        f1 = tmp_path / "a.md"
        f2 = tmp_path / "b.txt"
        f1.write_bytes(_MD)
        f2.write_bytes(_TEXT)
        c = UploadConnector()
        docs = list(c.harvest([str(f1), str(f2)]))
        assert len(docs) == 2
        source_types = {d.source_type for d in docs}
        assert source_types == {"note"}

    def test_harvest_paste(self):
        c = UploadConnector()
        docs = list(c.harvest([
            {"paste": "# Note A\nContent A", "title": "Note A"},
            {"paste": "# Note B\nContent B", "title": "Note B"},
        ]))
        assert len(docs) == 2
        titles = {d.title for d in docs}
        assert "Note A" in titles
        assert "Note B" in titles

    # --- registry ---------------------------------------------------------- #

    def test_registered_in_registry(self):
        import src.ingestion.connectors  # noqa: F401
        from src.ingestion.connectors.registry import is_registered
        assert is_registered("note")


# --------------------------------------------------------------------------- #
# _stable_id
# --------------------------------------------------------------------------- #

class TestStableId:
    def test_format(self):
        sid = _stable_id("/path/to/file.md")
        assert sid.startswith("upload:")
        assert len(sid) == len("upload:") + 12

    def test_stable(self):
        assert _stable_id("foo") == _stable_id("foo")

    def test_different_keys_differ(self):
        assert _stable_id("a") != _stable_id("b")
