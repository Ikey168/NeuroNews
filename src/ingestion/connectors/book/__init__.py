"""
Books connector: EPUB and PDF ingestion into document-ingest-v1 records.

Importing this package registers the ``book`` connector.
"""

from src.ingestion.connectors.book.connector import (
    BookConnector,
    book_metadata_to_documents,
)
from src.ingestion.connectors.book.epub_parser import parse_epub
from src.ingestion.connectors.book.models import BookMetadata, BookSection, book_id, section_id
from src.ingestion.connectors.book.pdf_parser import parse_pdf_sections

__all__ = [
    "BookConnector",
    "book_metadata_to_documents",
    "parse_epub",
    "parse_pdf_sections",
    "BookMetadata",
    "BookSection",
    "book_id",
    "section_id",
]
