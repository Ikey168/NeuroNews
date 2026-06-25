"""
EPUB parsing for books.

Uses ebooklib when installed (full structure: parts/chapters/sections from the
NCX/ToC spine). Falls back to stdlib zip+XML extraction which yields chapter
text without deep hierarchy. Both paths produce a BookMetadata with a section
tree ready for structure-aware chunking.
"""

from __future__ import annotations

import io
import re
import zipfile
from typing import List, Optional, Tuple
from xml.etree import ElementTree as ET

from src.ingestion.connectors.book.models import BookMetadata, BookSection


# Namespace maps used in both the fallback and the ebooklib path.
_NS_OPF = {"opf": "http://www.idpf.org/2007/opf"}
_NS_DC = {"dc": "http://purl.org/dc/elements/1.1/"}
_NS_NCX = {"ncx": "http://www.daisy.org/z3986/2005/ncx/"}


def _strip_tags(text: str) -> str:
    """Remove XML/HTML tags from a string."""
    return re.sub(r"<[^>]+>", " ", text).strip()


def _text_from_xhtml(xhtml_bytes: bytes) -> str:
    """Extract visible text from an XHTML document."""
    try:
        tree = ET.fromstring(xhtml_bytes)
        return " ".join(tree.itertext()).strip()
    except ET.ParseError:
        # Malformed XHTML: strip tags heuristically.
        return _strip_tags(xhtml_bytes.decode("utf-8", errors="replace"))


def _opf_metadata(opf_bytes: bytes) -> Tuple[str, List[str], Optional[str], Optional[str]]:
    """Parse OPF metadata: (title, authors, language, isbn)."""
    try:
        root = ET.fromstring(opf_bytes)
    except ET.ParseError:
        return ("", [], None, None)

    title = ""
    authors: List[str] = []
    language = None
    isbn = None

    meta = root.find("opf:metadata", _NS_OPF)
    if meta is None:
        # Some EPUBs omit the namespace prefix on the metadata element.
        meta = root.find("metadata")
    if meta is not None:
        t = meta.find("dc:title", _NS_DC)
        if t is None:
            t = meta.find("title")
        if t is not None and t.text:
            title = t.text.strip()
        for creator in list(meta.findall("dc:creator", _NS_DC)) + list(meta.findall("creator")):
            if creator.text:
                authors.append(creator.text.strip())
        lang = meta.find("dc:language", _NS_DC)
        if lang is None:
            lang = meta.find("language")
        if lang is not None and lang.text:
            language = lang.text.strip()[:2]  # "en-US" -> "en"
        for ident in list(meta.findall("dc:identifier", _NS_DC)) + list(meta.findall("identifier")):
            scheme = ident.get("{http://www.idpf.org/2007/opf}scheme", "")
            if "isbn" in scheme.lower() and ident.text:
                isbn = re.sub(r"[^0-9X]", "", ident.text.upper())

    return (title, authors, language, isbn)


def _ncx_sections(ncx_bytes: bytes, zip_file: zipfile.ZipFile, content_dir: str) -> List[BookSection]:
    """
    Parse the NCX navigation document to build a section tree.

    Each navPoint becomes a BookSection; the text is fetched from the
    referenced content file. The tree preserves part/chapter nesting.
    """
    try:
        root = ET.fromstring(ncx_bytes)
    except ET.ParseError:
        return []

    def nav_label(nav_point: ET.Element) -> str:
        label = nav_point.find("ncx:navLabel/ncx:text", _NS_NCX)
        return label.text.strip() if label is not None and label.text else ""

    def content_src(nav_point: ET.Element) -> Optional[str]:
        content = nav_point.find("ncx:content", _NS_NCX)
        if content is not None:
            return content.get("src", "").split("#")[0]
        return None

    seen_srcs: set = set()

    def _read_text(src: str) -> str:
        if not src or src in seen_srcs:
            return ""
        seen_srcs.add(src)
        candidate = f"{content_dir}/{src}".lstrip("/")
        try:
            return _text_from_xhtml(zip_file.read(candidate))
        except KeyError:
            # Try without directory prefix
            try:
                return _text_from_xhtml(zip_file.read(src))
            except KeyError:
                return ""

    def build_section(nav_point: ET.Element, level: int) -> BookSection:
        title = nav_label(nav_point)
        src = content_src(nav_point)
        text = _read_text(src) if src else ""
        children = [
            build_section(child, level + 1)
            for child in nav_point.findall("ncx:navPoint", _NS_NCX)
        ]
        return BookSection(title=title, text=text, level=level, children=children)

    nav_map = root.find("ncx:navMap", _NS_NCX)
    if nav_map is None:
        return []
    return [
        build_section(np, 0)
        for np in nav_map.findall("ncx:navPoint", _NS_NCX)
    ]


def _spine_sections(opf_bytes: bytes, zip_file: zipfile.ZipFile, content_dir: str) -> List[BookSection]:
    """
    Fallback when there is no NCX: parse the OPF spine to get document order
    and extract text from each spine item.
    """
    try:
        root = ET.fromstring(opf_bytes)
    except ET.ParseError:
        return []

    manifest = root.find("opf:manifest", _NS_OPF)
    if manifest is None:
        manifest = root.find("manifest")
    spine = root.find("opf:spine", _NS_OPF)
    if spine is None:
        spine = root.find("spine")
    if manifest is None or spine is None:
        return []

    ns_items = manifest.findall("opf:item", _NS_OPF) or manifest.findall("item")
    id_to_href = {
        item.get("id", ""): item.get("href", "")
        for item in ns_items
        if item.get("media-type", "").startswith("application/xhtml")
        or item.get("media-type", "") == "text/html"
    }

    ns_itemrefs = spine.findall("opf:itemref", _NS_OPF) or spine.findall("itemref")
    sections = []
    for itemref in ns_itemrefs:
        idref = itemref.get("idref", "")
        href = id_to_href.get(idref, "")
        if not href:
            continue
        candidate = f"{content_dir}/{href}".lstrip("/")
        try:
            text = _text_from_xhtml(zip_file.read(candidate))
        except KeyError:
            try:
                text = _text_from_xhtml(zip_file.read(href))
            except KeyError:
                continue
        sections.append(BookSection(title=href, text=text, level=1))
    return sections


def parse_epub(epub_bytes: bytes, file_path: Optional[str] = None) -> BookMetadata:
    """
    Parse an EPUB file into a BookMetadata with a hierarchical section tree.

    Tries ebooklib first (richer structure); falls back to stdlib zip+XML so
    the parser works without optional dependencies.
    """
    # --- Try ebooklib (best structure extraction) ----------------------- #
    try:
        return _parse_epub_ebooklib(epub_bytes, file_path)
    except Exception:
        pass

    # --- Fallback: stdlib zip+XML --------------------------------------- #
    return _parse_epub_stdlib(epub_bytes, file_path)


def _parse_epub_ebooklib(epub_bytes: bytes, file_path: Optional[str]) -> BookMetadata:
    import ebooklib  # type: ignore
    from ebooklib import epub as eblib_epub  # type: ignore

    book = eblib_epub.read_epub(io.BytesIO(epub_bytes))

    title = book.title or ""
    authors = list(book.get_metadata("DC", "creator") or [])
    authors = [a[0] if isinstance(a, (list, tuple)) else str(a) for a in authors]
    language_meta = book.get_metadata("DC", "language")
    language = (language_meta[0][0][:2] if language_meta else "en")

    isbn = None
    for ident, _ in (book.get_metadata("DC", "identifier") or []):
        if "isbn" in str(ident).lower():
            isbn = re.sub(r"[^0-9X]", "", str(ident).upper())
            break

    toc = book.toc
    sections = _ebooklib_toc_to_sections(book, toc, level=0)
    if not sections:
        # No ToC: walk the spine in order.
        sections = [
            BookSection(title=item.get_name(), text=_text_from_xhtml(item.get_content()), level=1)
            for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT)
            if item.get_content()
        ]

    return BookMetadata(
        title=title,
        authors=authors,
        language=language,
        isbn=isbn,
        file_path=file_path,
        format="epub",
        sections=sections,
        extractor="ebooklib",
    )


def _ebooklib_toc_to_sections(book, toc_items, level: int) -> List[BookSection]:
    """Recursively convert ebooklib ToC items to BookSections."""
    from ebooklib import epub as eblib_epub  # type: ignore

    sections = []
    for item in toc_items:
        if isinstance(item, eblib_epub.Link):
            # Leaf node: fetch the referenced document.
            title = item.title or ""
            href = item.href.split("#")[0] if item.href else ""
            text = ""
            if href:
                try:
                    doc = book.get_item_with_href(href)
                    if doc is not None:
                        text = _text_from_xhtml(doc.get_content())
                except Exception:
                    pass
            sections.append(BookSection(title=title, text=text, level=level))
        elif isinstance(item, tuple) and len(item) == 2:
            # (Section, [children]) or (Link, [children])
            parent, children = item
            title = getattr(parent, "title", "") or ""
            href = getattr(parent, "href", "").split("#")[0] if getattr(parent, "href", "") else ""
            text = ""
            if href:
                try:
                    doc = book.get_item_with_href(href)
                    if doc is not None:
                        text = _text_from_xhtml(doc.get_content())
                except Exception:
                    pass
            child_sections = _ebooklib_toc_to_sections(book, children or [], level + 1)
            sections.append(BookSection(title=title, text=text, level=level, children=child_sections))
    return sections


def _parse_epub_stdlib(epub_bytes: bytes, file_path: Optional[str]) -> BookMetadata:
    """Parse EPUB using only the Python standard library."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(epub_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError(f"Not a valid EPUB/ZIP file: {exc}") from exc

    names = set(zf.namelist())

    # Locate the OPF via META-INF/container.xml
    opf_path = ""
    if "META-INF/container.xml" in names:
        container = ET.fromstring(zf.read("META-INF/container.xml"))
        rootfile = container.find(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile")
        if rootfile is not None:
            opf_path = rootfile.get("full-path", "")

    if not opf_path:
        # Heuristic: find any .opf file.
        for name in names:
            if name.endswith(".opf"):
                opf_path = name
                break

    content_dir = "/".join(opf_path.split("/")[:-1]) if "/" in opf_path else ""

    opf_bytes = zf.read(opf_path) if opf_path in names else b""
    title, authors, language, isbn = _opf_metadata(opf_bytes)

    # Try NCX navigation document first.
    sections: List[BookSection] = []
    ncx_path = f"{content_dir}/toc.ncx".lstrip("/")
    if ncx_path not in names:
        # Search for any .ncx file under content_dir.
        for name in names:
            if name.endswith(".ncx"):
                ncx_path = name
                break
    if ncx_path in names:
        sections = _ncx_sections(zf.read(ncx_path), zf, content_dir)

    if not sections and opf_bytes:
        sections = _spine_sections(opf_bytes, zf, content_dir)

    return BookMetadata(
        title=title or (file_path or "unknown"),
        authors=authors,
        language=language or "en",
        isbn=isbn,
        file_path=file_path,
        format="epub",
        sections=sections,
        extractor="stdlib",
    )
