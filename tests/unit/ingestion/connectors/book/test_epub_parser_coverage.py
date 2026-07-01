"""
Coverage-focused tests for src/ingestion/connectors/book/epub_parser.py.

Exercises the stdlib zip+XML fallback path (NCX + spine), the OPF metadata
parser, XHTML text extraction, malformed-input branches, and the ebooklib
path via a stubbed ``ebooklib`` module. Builds tiny in-memory EPUB archives.
"""

import io
import sys
import types
import zipfile

import pytest

from src.ingestion.connectors.book import epub_parser as ep
from src.ingestion.connectors.book.models import BookMetadata, BookSection


# --------------------------------------------------------------------------- #
# Helpers to build a minimal in-memory EPUB
# --------------------------------------------------------------------------- #

CONTAINER_XML = (
    '<?xml version="1.0"?>'
    '<container version="1.0" '
    'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    '<rootfiles><rootfile full-path="OEBPS/content.opf" '
    'media-type="application/oebps-package+xml"/></rootfiles></container>'
)

OPF_XML = (
    '<?xml version="1.0"?>'
    '<package xmlns="http://www.idpf.org/2007/opf" version="2.0">'
    '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
    '<dc:title>My Test Book</dc:title>'
    '<dc:creator>Ada Lovelace</dc:creator>'
    '<dc:language>en-US</dc:language>'
    '<dc:identifier opf:scheme="ISBN" '
    'xmlns:opf="http://www.idpf.org/2007/opf">978-0-13-4X9-a</dc:identifier>'
    '</metadata>'
    '<manifest>'
    '<item id="c1" href="chap1.xhtml" media-type="application/xhtml+xml"/>'
    '<item id="c2" href="chap2.xhtml" media-type="text/html"/>'
    '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
    '</manifest>'
    '<spine toc="ncx"><itemref idref="c1"/><itemref idref="c2"/></spine>'
    '</package>'
)

NCX_XML = (
    '<?xml version="1.0"?>'
    '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
    '<navMap>'
    '<navPoint id="np1"><navLabel><text>Chapter One</text></navLabel>'
    '<content src="chap1.xhtml"/>'
    '<navPoint id="np1a"><navLabel><text>Section 1.1</text></navLabel>'
    '<content src="chap1.xhtml#sec"/></navPoint>'
    '</navPoint>'
    '<navPoint id="np2"><navLabel><text>Chapter Two</text></navLabel>'
    '<content src="chap2.xhtml"/></navPoint>'
    '</navMap></ncx>'
)

CHAP1 = b'<html><body><p>Hello from chapter one.</p></body></html>'
CHAP2 = b'<html><body><p>Second chapter body text.</p></body></html>'


def _build_epub(*, with_ncx=True, container=True, opf=OPF_XML):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        if container:
            zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/chap1.xhtml", CHAP1)
        zf.writestr("OEBPS/chap2.xhtml", CHAP2)
        if with_ncx:
            zf.writestr("OEBPS/toc.ncx", NCX_XML)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _no_ebooklib(monkeypatch):
    """Force the stdlib fallback for tests that don't stub ebooklib.

    epub_parser imports ebooklib lazily inside _parse_epub_ebooklib; removing
    it from sys.modules and blocking import makes _parse_epub route to stdlib.
    """
    monkeypatch.setitem(sys.modules, "ebooklib", None)  # import -> ImportError
    yield


# --------------------------------------------------------------------------- #
# Low-level helper coverage
# --------------------------------------------------------------------------- #

def test_strip_tags_removes_markup():
    assert ep._strip_tags("<b>bold</b> text") == "bold  text".replace("  ", "  ")
    # exact: tags become spaces then .strip()
    assert ep._strip_tags("<p>a</p>") == "a"


def test_text_from_xhtml_wellformed():
    out = ep._text_from_xhtml(b"<html><body>hi there</body></html>")
    assert "hi there" in out


def test_text_from_xhtml_malformed_falls_back_to_strip():
    # Unclosed tag -> ParseError -> heuristic strip path (lines 37-39).
    out = ep._text_from_xhtml(b"<html><body>broken <b>text")
    assert "broken" in out and "text" in out
    assert "<" not in out


def test_opf_metadata_parse_error_returns_empty():
    assert ep._opf_metadata(b"<<<not xml") == ("", [], None, None)


def test_opf_metadata_extracts_all_fields():
    title, authors, language, isbn = ep._opf_metadata(OPF_XML.encode())
    assert title == "My Test Book"
    assert authors == ["Ada Lovelace"]
    assert language == "en"  # "en-US" truncated to 2 chars
    assert isbn == "9780134X9"  # non [0-9X] chars stripped, uppercased


def test_opf_metadata_no_namespace_prefix():
    opf = (
        '<package><metadata>'
        '<title>Plain</title><creator>Bob</creator>'
        '<language>fr</language>'
        '<identifier opf:scheme="ISBN" '
        'xmlns:opf="http://www.idpf.org/2007/opf">12345</identifier>'
        '</metadata></package>'
    )
    title, authors, language, isbn = ep._opf_metadata(opf.encode())
    assert title == "Plain"
    assert authors == ["Bob"]
    assert language == "fr"
    assert isbn == "12345"


# --------------------------------------------------------------------------- #
# NCX section building
# --------------------------------------------------------------------------- #

def test_ncx_sections_parse_error_returns_empty():
    zf = zipfile.ZipFile(io.BytesIO(_build_epub()))
    assert ep._ncx_sections(b"broken", zf, "OEBPS") == []


def test_ncx_sections_no_navmap_returns_empty():
    ncx = ('<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/">'
           '</ncx>')
    zf = zipfile.ZipFile(io.BytesIO(_build_epub()))
    assert ep._ncx_sections(ncx.encode(), zf, "OEBPS") == []


def test_ncx_sections_builds_nested_tree_and_dedupes_src():
    zf = zipfile.ZipFile(io.BytesIO(_build_epub()))
    sections = ep._ncx_sections(NCX_XML.encode(), zf, "OEBPS")
    assert len(sections) == 2
    ch1 = sections[0]
    assert ch1.title == "Chapter One"
    assert "chapter one" in ch1.text.lower()
    # Nested child section present
    assert len(ch1.children) == 1
    assert ch1.children[0].title == "Section 1.1"
    # chap1.xhtml already consumed by parent -> child dedup returns "".
    assert ch1.children[0].text == ""
    assert sections[1].title == "Chapter Two"
    assert "second chapter" in sections[1].text.lower()


def test_ncx_sections_missing_content_file_yields_empty_text():
    # NCX points at a file that isn't in the zip -> _read_text KeyError paths.
    ncx = (
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/">'
        '<navMap><navPoint><navLabel><text>Ghost</text></navLabel>'
        '<content src="missing.xhtml"/></navPoint></navMap></ncx>'
    )
    zf = zipfile.ZipFile(io.BytesIO(_build_epub()))
    sections = ep._ncx_sections(ncx.encode(), zf, "OEBPS")
    assert len(sections) == 1
    assert sections[0].title == "Ghost"
    assert sections[0].text == ""


def test_ncx_sections_root_relative_src_fallback():
    # File exists at root (no content_dir prefix) -> second read branch.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("root_chap.xhtml", b"<html><body>root text</body></html>")
    zf = zipfile.ZipFile(io.BytesIO(buf.getvalue()))
    ncx = (
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/">'
        '<navMap><navPoint><navLabel><text>R</text></navLabel>'
        '<content src="root_chap.xhtml"/></navPoint></navMap></ncx>'
    )
    sections = ep._ncx_sections(ncx.encode(), zf, "OEBPS")
    assert "root text" in sections[0].text


# --------------------------------------------------------------------------- #
# Spine section building (fallback when no NCX)
# --------------------------------------------------------------------------- #

def test_spine_sections_parse_error_returns_empty():
    zf = zipfile.ZipFile(io.BytesIO(_build_epub()))
    assert ep._spine_sections(b"<<bad", zf, "OEBPS") == []


def test_spine_sections_missing_manifest_returns_empty():
    opf = ('<package xmlns="http://www.idpf.org/2007/opf">'
           '<spine><itemref idref="c1"/></spine></package>')
    zf = zipfile.ZipFile(io.BytesIO(_build_epub()))
    assert ep._spine_sections(opf.encode(), zf, "OEBPS") == []


def test_spine_sections_reads_documents_in_order():
    zf = zipfile.ZipFile(io.BytesIO(_build_epub()))
    sections = ep._spine_sections(OPF_XML.encode(), zf, "OEBPS")
    assert [s.title for s in sections] == ["chap1.xhtml", "chap2.xhtml"]
    assert "chapter one" in sections[0].text.lower()


def test_spine_sections_skips_unknown_idref_and_missing_files():
    # idref c3 has no manifest href -> skipped (continue at line 170).
    opf = (
        '<package xmlns="http://www.idpf.org/2007/opf">'
        '<manifest>'
        '<item id="c1" href="chap1.xhtml" media-type="application/xhtml+xml"/>'
        '</manifest>'
        '<spine><itemref idref="c1"/><itemref idref="c3"/></spine>'
        '</package>'
    )
    zf = zipfile.ZipFile(io.BytesIO(_build_epub()))
    sections = ep._spine_sections(opf.encode(), zf, "OEBPS")
    assert len(sections) == 1


# --------------------------------------------------------------------------- #
# parse_epub (stdlib path end to end)
# --------------------------------------------------------------------------- #

def test_parse_epub_stdlib_with_ncx():
    meta = ep.parse_epub(_build_epub(with_ncx=True), file_path="/tmp/book.epub")
    assert isinstance(meta, BookMetadata)
    assert meta.extractor == "stdlib"
    assert meta.title == "My Test Book"
    assert meta.authors == ["Ada Lovelace"]
    assert meta.format == "epub"
    # NCX drove section building.
    assert [s.title for s in meta.sections] == ["Chapter One", "Chapter Two"]


def test_parse_epub_stdlib_without_ncx_uses_spine():
    meta = ep.parse_epub(_build_epub(with_ncx=False))
    assert meta.extractor == "stdlib"
    assert [s.title for s in meta.sections] == ["chap1.xhtml", "chap2.xhtml"]


def test_parse_epub_stdlib_no_container_finds_opf_heuristically():
    meta = ep.parse_epub(_build_epub(container=False))
    # Falls back to scanning for a *.opf file.
    assert meta.title == "My Test Book"


def test_parse_epub_bad_zip_raises_valueerror_via_stdlib():
    # ebooklib blocked -> stdlib path -> BadZipFile -> ValueError.
    with pytest.raises(ValueError):
        ep.parse_epub(b"this is not a zip file at all")


def test_parse_epub_stdlib_missing_metadata_uses_file_path_title():
    # OPF with empty metadata -> title falls back to file_path.
    empty_opf = ('<package xmlns="http://www.idpf.org/2007/opf">'
                 '<metadata></metadata>'
                 '<manifest></manifest><spine></spine></package>')
    epub = _build_epub(with_ncx=False, opf=empty_opf)
    meta = ep.parse_epub(epub, file_path="/books/anon.epub")
    assert meta.title == "/books/anon.epub"
    assert meta.language == "en"


# --------------------------------------------------------------------------- #
# ebooklib path via a stub module
# --------------------------------------------------------------------------- #

class _StubLink:
    def __init__(self, title, href):
        self.title = title
        self.href = href


class _StubDoc:
    def __init__(self, name, content):
        self._name = name
        self._content = content

    def get_name(self):
        return self._name

    def get_content(self):
        return self._content


class _StubBook:
    def __init__(self):
        self.title = "Stub Book"
        self._items = {
            "a.xhtml": _StubDoc("a.xhtml", b"<p>alpha body</p>"),
            "b.xhtml": _StubDoc("b.xhtml", b"<p>beta body</p>"),
        }
        # A tuple (Section-ish, [children]) plus a bare Link leaf.
        parent = _StubLink("Part I", "a.xhtml")
        child = _StubLink("Chapter A", "a.xhtml")
        self.toc = [(parent, [child]), _StubLink("Standalone", "b.xhtml")]

    def get_metadata(self, ns, name):
        data = {
            "creator": [("Grace Hopper", {})],
            "language": [("de", {})],
            "identifier": [("urn:isbn:99999", {})],
        }
        return data.get(name, [])

    def get_item_with_href(self, href):
        return self._items.get(href)

    def get_items_of_type(self, _t):
        return list(self._items.values())


def _install_ebooklib_stub(monkeypatch, book):
    eblib = types.ModuleType("ebooklib")
    eblib.ITEM_DOCUMENT = 9
    epub_mod = types.ModuleType("ebooklib.epub")
    epub_mod.Link = _StubLink

    def read_epub(_stream):
        return book

    epub_mod.read_epub = read_epub
    eblib.epub = epub_mod
    monkeypatch.setitem(sys.modules, "ebooklib", eblib)
    monkeypatch.setitem(sys.modules, "ebooklib.epub", epub_mod)


def test_parse_epub_ebooklib_path(monkeypatch):
    book = _StubBook()
    _install_ebooklib_stub(monkeypatch, book)
    meta = ep.parse_epub(b"ignored-bytes", file_path="/x.epub")
    assert meta.extractor == "ebooklib"
    assert meta.title == "Stub Book"
    assert meta.authors == ["Grace Hopper"]
    assert meta.language == "de"
    assert meta.isbn == "99999"
    # ToC produced a nested part with a chapter child and a standalone leaf.
    titles = [s.title for s in meta.sections]
    assert "Part I" in titles and "Standalone" in titles
    part = next(s for s in meta.sections if s.title == "Part I")
    assert [c.title for c in part.children] == ["Chapter A"]
    assert "alpha body" in part.text


def test_parse_epub_ebooklib_no_toc_walks_spine(monkeypatch):
    book = _StubBook()
    book.toc = []  # empty ToC -> spine walk branch (lines 221-226)
    _install_ebooklib_stub(monkeypatch, book)
    meta = ep.parse_epub(b"ignored")
    assert meta.extractor == "ebooklib"
    names = [s.title for s in meta.sections]
    assert names == ["a.xhtml", "b.xhtml"]


def test_ebooklib_toc_link_with_missing_doc(monkeypatch):
    book = _StubBook()
    # Link points at href not present -> get_item_with_href returns None.
    book.toc = [_StubLink("Ghost", "missing.xhtml")]
    _install_ebooklib_stub(monkeypatch, book)
    meta = ep.parse_epub(b"ignored")
    assert meta.sections[0].title == "Ghost"
    assert meta.sections[0].text == ""


class _RaisingDoc(_StubDoc):
    def get_content(self):
        raise RuntimeError("boom reading content")


def test_ebooklib_toc_get_content_exception_is_swallowed(monkeypatch):
    book = _StubBook()
    book._items["a.xhtml"] = _RaisingDoc("a.xhtml", b"x")
    # Leaf Link + tuple parent both reference a.xhtml which now raises.
    parent = _StubLink("Part", "a.xhtml")
    book.toc = [_StubLink("Leaf", "a.xhtml"), (parent, [])]
    _install_ebooklib_stub(monkeypatch, book)
    meta = ep.parse_epub(b"ignored")
    # Exceptions are caught -> text stays empty but sections still built.
    titles = [s.title for s in meta.sections]
    assert "Leaf" in titles and "Part" in titles
    assert all(s.text == "" for s in meta.sections)


def test_parse_epub_stdlib_ncx_nonstandard_name_and_location():
    # NCX not at content_dir/toc.ncx -> triggers the *.ncx search (313-314),
    # and the itemref file lives at zip root so the spine reader's second
    # read branch (174-178) is used too.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", OPF_XML)
        # Chapter files at the archive root (not under OEBPS/).
        zf.writestr("chap1.xhtml", CHAP1)
        zf.writestr("chap2.xhtml", CHAP2)
        # NCX under a differently-named path.
        zf.writestr("OEBPS/nav-doc.ncx", NCX_XML)
    meta = ep.parse_epub(buf.getvalue())
    assert meta.extractor == "stdlib"
    # NCX found via search; text read via root fallback.
    ch1 = meta.sections[0]
    assert ch1.title == "Chapter One"
    assert "chapter one" in ch1.text.lower()
