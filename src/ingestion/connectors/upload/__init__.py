"""
Upload connector: ingest arbitrary documents (PDF, Markdown, DOCX, text, email)
as document-ingest-v1 ``Document`` records with ``source_type="note"``.

Importing this package registers the ``note`` connector.
"""

from src.ingestion.connectors.upload.connector import UploadConnector
from src.ingestion.connectors.upload.detectors import detect_format, detect_encoding, normalize_format
from src.ingestion.connectors.upload.parsers import extract_text

__all__ = [
    "UploadConnector",
    "detect_format",
    "detect_encoding",
    "normalize_format",
    "extract_text",
]
