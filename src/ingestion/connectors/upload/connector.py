"""
Upload connector: ingest arbitrary documents (PDF, Markdown, DOCX, plain text,
email) as ``Document`` records with ``source_type="note"``.

Implements the connector interface (discover → fetch → parse → Document) for
the "second brain" / personal knowledge-base use case: drop in mixed docs and
get cross-corpus, cross-source-type cited Q&A.

Two input modes, both accepted by ``discover()``:

  **File paths**::

      connector.harvest(["/notes/meeting.md", "/papers/report.pdf"])

  **Paste** (in-memory text, no file required)::

      connector.harvest([
          {"paste": "# My Note\\nKey insight here.", "title": "Quick Note"},
      ])

  Both modes can be mixed in the same query list.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from services.ingest.common.document_model import Document
from src.ingestion.connectors.base import Connector, RawDocument, SourceRef
from src.ingestion.connectors.registry import register_connector
from src.ingestion.connectors.upload.detectors import detect_format, normalize_format
from src.ingestion.connectors.upload.parsers import extract_text

_PASTE_SCHEME = "paste://"
_SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".md", ".markdown", ".mdown", ".mkd", ".rst",
    ".html", ".htm", ".xhtml", ".eml", ".msg", ".mbox",
    ".txt", ".text", ".csv", ".tsv", ".log", ".rtf", ".xml",
}


def _stable_id(key: str) -> str:
    digest = hashlib.md5(key.encode()).hexdigest()[:12]
    return f"upload:{digest}"


def _title_from_text(text: str, fallback: str) -> str:
    """Return the first non-empty line of text as a title, up to 120 chars."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:120]
    return fallback


def _build_document(
    doc_id: str,
    title: str,
    text: str,
    language: str,
    fmt: str,
    source_ref: str,
    extra_metadata: Dict[str, Any],
    ingested_at: int,
) -> Optional[Document]:
    if not text.strip():
        return None
    metadata: Dict[str, Any] = {
        "format": fmt,
        **{k: v for k, v in extra_metadata.items() if v not in (None, "", [])},
    }
    return Document(
        document_id=doc_id,
        source_type="note",
        language=language,
        ingested_at=ingested_at,
        title=title,
        content=text,
        content_ref=source_ref,
        url=source_ref if not source_ref.startswith(_PASTE_SCHEME) else None,
        metadata=metadata,
    )


@register_connector
class UploadConnector(Connector):
    """
    Ingest arbitrary uploaded documents as ``source_type="note"`` Documents.

    Supports: PDF, Markdown, DOCX/DOC, plain text, HTML/XML, email (.eml).

    ``discover(query)`` accepts a list of:
    - ``str`` / ``Path``: local file paths.
    - ``dict`` with key ``"paste"``: in-memory text content.
      Optional keys: ``"title"`` (str), ``"language"`` (str, default "en").

    ``parse()`` auto-detects the format from the file extension and magic bytes,
    extracts text, and returns a single Document per input.
    """

    source_type = "note"

    def __init__(self, default_language: str = "en") -> None:
        self._default_language = default_language

    def discover(self, query: Optional[Any] = None) -> Iterable[SourceRef]:
        if query is None:
            return
        items = [query] if isinstance(query, (str, Path, dict)) else list(query)
        for item in items:
            if isinstance(item, dict) and "paste" in item:
                yield self._paste_ref(item)
            else:
                path = Path(str(item))
                yield SourceRef(
                    locator=str(path.resolve()),
                    title=path.stem,
                    metadata={"format": path.suffix.lstrip(".").lower()},
                )

    @staticmethod
    def _paste_ref(item: dict) -> SourceRef:
        content = item.get("paste", "")
        title = item.get("title", "Pasted Note")
        language = item.get("language", "en")
        doc_id = _stable_id(content[:200])
        return SourceRef(
            locator=f"{_PASTE_SCHEME}{doc_id}",
            title=title,
            metadata={
                "paste": True,
                "content": content,
                "language": language,
                "format": "markdown" if content.lstrip().startswith("#") else "text",
            },
        )

    def fetch(self, ref: SourceRef) -> RawDocument:
        if ref.locator.startswith(_PASTE_SCHEME):
            raw = ref.metadata.get("content", "").encode("utf-8")
            ct = "text/markdown" if ref.metadata.get("format") == "markdown" else "text/plain"
            return RawDocument(ref=ref, content=raw, content_type=ct)

        path = Path(ref.locator)
        if not path.exists():
            raise FileNotFoundError(f"Upload file not found: {path}")
        suffix = path.suffix.lower()
        if suffix and suffix not in _SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file extension {suffix!r} for {path.name}; "
                f"supported: {sorted(_SUPPORTED_EXTENSIONS)}"
            )
        return RawDocument(
            ref=ref,
            content=path.read_bytes(),
            content_type=f"application/{suffix.lstrip('.') or 'octet-stream'}",
        )

    def parse(self, raw: RawDocument) -> List[Document]:
        content = raw.content if isinstance(raw.content, bytes) else raw.content.encode()
        ref = raw.ref
        is_paste = ref.locator.startswith(_PASTE_SCHEME)

        raw_fmt = ref.metadata.get("format") or ""
        fmt = normalize_format(raw_fmt) if raw_fmt else detect_format(content, ref.title or "")
        language = ref.metadata.get("language", self._default_language)

        text, meta = extract_text(content, fmt)

        # Title resolution: parser metadata → ref.title → first line of text
        title = (
            meta.get("title")
            or meta.get("subject")
            or ref.title
            or _title_from_text(text, "Untitled")
        )

        if is_paste:
            doc_id = _stable_id(content[:200].decode("utf-8", errors="replace"))
            source_ref = ref.locator
        else:
            doc_id = _stable_id(ref.locator)
            source_ref = f"file://{ref.locator}"

        doc = _build_document(
            doc_id=doc_id,
            title=str(title),
            text=text,
            language=language,
            fmt=fmt,
            source_ref=source_ref,
            extra_metadata=meta,
            ingested_at=raw.fetched_at,
        )
        return [doc] if doc is not None else []
