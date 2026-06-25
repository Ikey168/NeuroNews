"""
Books connector: ingest EPUB and PDF books as structured Document records.

Implements the connector interface (discover -> fetch -> parse -> Document)
for source_type="book". Each chapter / top-level section becomes its own
Document record so retrieval can cite "Chapter 3 > The Turing Test". Large
bodies are stored inline; content_ref carries a file URI fragment for the
section's location in the source file.

Usage::

    connector = BookConnector()
    for doc in connector.harvest(["path/to/book.epub", "path/to/book.pdf"]):
        # doc.metadata["section_path"] -> ["Part I", "Chapter 3", "..."]
        chunks = chunk_document(doc)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, List, Optional

from services.ingest.common.document_model import Document
from src.ingestion.connectors.base import Connector, RawDocument, SourceRef
from src.ingestion.connectors.book.epub_parser import parse_epub
from src.ingestion.connectors.book.models import BookMetadata, BookSection, section_id
from src.ingestion.connectors.book.pdf_parser import parse_pdf_sections
from src.ingestion.connectors.registry import register_connector


def _file_uri(path: str, fragment: str = "") -> str:
    uri = f"file://{Path(path).resolve()}"
    return f"{uri}#{fragment}" if fragment else uri


def book_metadata_to_documents(meta: BookMetadata, ingested_at: int) -> List[Document]:
    """
    Turn a BookMetadata (with section tree) into one Document per chapter/section.

    Top-level sections without body text become container nodes whose children
    are still emitted. Sections with both body text and children emit a Document
    for themselves and their children.
    """
    docs: List[Document] = []

    def _emit(node: BookSection, ancestors: List[str]) -> None:
        path = node.path_from(ancestors)
        fragment = "/".join(p.lower().replace(" ", "-") for p in path if p)
        doc_id = section_id(meta.document_id, path)
        content_ref = _file_uri(meta.file_path, fragment) if meta.file_path else None

        if node.text.strip():
            docs.append(Document(
                document_id=doc_id,
                source_type="book",
                language=meta.language,
                ingested_at=ingested_at,
                source_id=meta.isbn or None,
                url=content_ref,
                title=f"{meta.title} › {' › '.join(p for p in path if p)}" if path else meta.title,
                content=node.text,
                content_ref=content_ref,
                authors=list(meta.authors),
                metadata={
                    "book_title": meta.title,
                    "book_id": meta.document_id,
                    "section_path": list(path),
                    "section_level": node.level,
                    "format": meta.format,
                    "extractor": meta.extractor,
                    **({"isbn": meta.isbn} if meta.isbn else {}),
                    **({"publisher": meta.publisher} if meta.publisher else {}),
                    **({"published_year": meta.published_year} if meta.published_year else {}),
                },
            ))

        for child in node.children:
            _emit(child, path)

    for section in meta.sections:
        _emit(section, [])

    # If the book has no sections at all, emit one Document for the whole book.
    if not docs and (meta.title or meta.file_path):
        all_text = " ".join(
            s.text for s in meta.sections if s.text
        )
        if all_text.strip():
            docs.append(Document(
                document_id=meta.document_id,
                source_type="book",
                language=meta.language,
                ingested_at=ingested_at,
                source_id=meta.isbn or None,
                url=_file_uri(meta.file_path) if meta.file_path else None,
                title=meta.title,
                content=all_text,
                content_ref=_file_uri(meta.file_path) if meta.file_path else None,
                authors=list(meta.authors),
                metadata={
                    "book_title": meta.title,
                    "book_id": meta.document_id,
                    "section_path": [],
                    "format": meta.format,
                    "extractor": meta.extractor,
                },
            ))

    return docs


@register_connector
class BookConnector(Connector):
    """
    Ingest EPUB and PDF books as document-ingest-v1 records.

    discover(query) expects a list of file paths (str or Path).
    Each chapter / top-level section becomes a separate Document so that
    RAG retrieval can cite "Chapter 3, The Turing Test".
    """

    source_type = "book"

    def discover(self, query: Optional[Any] = None) -> Iterable[SourceRef]:
        if query is None:
            return
        paths = [query] if isinstance(query, (str, Path)) else list(query)
        for path in paths:
            p = Path(path)
            yield SourceRef(
                locator=str(p.resolve()),
                title=p.stem,
                metadata={"format": p.suffix.lstrip(".").lower()},
            )

    def fetch(self, ref: SourceRef) -> RawDocument:
        path = Path(ref.locator)
        if not path.exists():
            raise FileNotFoundError(f"Book file not found: {path}")
        suffix = path.suffix.lower()
        content_type = (
            "application/epub+zip" if suffix == ".epub"
            else "application/pdf" if suffix == ".pdf"
            else "application/octet-stream"
        )
        return RawDocument(ref=ref, content=path.read_bytes(), content_type=content_type)

    def parse(self, raw: RawDocument) -> List[Document]:
        content_type = raw.content_type or ""
        path = raw.ref.locator
        content = raw.content
        if isinstance(content, str):
            content = content.encode("utf-8")

        if "epub" in content_type or path.endswith(".epub"):
            meta = parse_epub(content, file_path=path)
        elif "pdf" in content_type or path.endswith(".pdf"):
            sections, extractor = parse_pdf_sections(content)
            meta = BookMetadata(
                title=raw.ref.title or Path(path).stem,
                file_path=path,
                format="pdf",
                sections=sections,
                extractor=extractor,
            )
        else:
            raise ValueError(
                f"Unsupported content type {content_type!r} for {path!r}; "
                "expected .epub or .pdf"
            )

        return book_metadata_to_documents(meta, raw.fetched_at)
