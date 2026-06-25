"""
Format detection for the upload connector.

Identifies the document format from file bytes and filename so the right
parser is called. Uses, in order:
  1. File extension (fast, reliable for user uploads)
  2. Magic byte signatures (content-based, works for renamed files)
  3. Content heuristics (markdown markers checked before python-magic so
     that "# Heading" text isn't misclassified as text/plain)
  4. python-magic MIME type (if installed), for binary/unusual formats
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


# Maps file extension → format tag used by parsers.py
_EXT_TO_FORMAT: dict = {
    ".pdf":      "pdf",
    ".docx":     "docx",
    ".doc":      "docx",
    ".md":       "markdown",
    ".markdown": "markdown",
    ".mdown":    "markdown",
    ".mkd":      "markdown",
    ".rst":      "markdown",   # treat reStructuredText as plain markdown-ish
    ".html":     "html",
    ".htm":      "html",
    ".xhtml":    "html",
    ".eml":      "email",
    ".msg":      "email",
    ".mbox":     "email",
    ".txt":      "text",
    ".text":     "text",
    ".csv":      "text",
    ".tsv":      "text",
    ".log":      "text",
    ".rtf":      "text",
    ".xml":      "html",   # use HTML parser (tag-stripping) for XML
}

# Leading byte signatures → format tag
_MAGIC_SIGS: list = [
    (b"%PDF",           "pdf"),
    (b"PK\x03\x04",    "docx"),    # ZIP-based: DOCX, XLSX, PPTX, EPUB
    (b"\xd0\xcf\x11\xe0", "docx"), # OLE2 (legacy .doc)
    (b"From ",          "email"),
    (b"Return-Path:",   "email"),
    (b"Received:",      "email"),
    (b"MIME-Version:",  "email"),
    (b"<!DOCTYPE html", "html"),
    (b"<!doctype html", "html"),
    (b"<html",          "html"),
    (b"<HTML",          "html"),
    (b"<?xml",          "html"),
]


def detect_format(content: bytes, filename: str = "") -> str:
    """Return a format tag for the given file content and optional filename.

    Tags: "pdf", "docx", "markdown", "html", "email", "text"
    """
    # 1. Extension
    if filename:
        ext = Path(filename).suffix.lower()
        if ext in _EXT_TO_FORMAT:
            return _EXT_TO_FORMAT[ext]

    # 2. Magic bytes
    for sig, fmt in _MAGIC_SIGS:
        if content[:len(sig)].lower() == sig.lower():
            return fmt

    # 3. Content heuristics (before python-magic so markdown headings aren't
    #    misclassified as text/plain by the MIME detector)
    try:
        text_preview = content.decode("utf-8")
        lines = text_preview.splitlines()[:20]
        if any(ln.startswith("#") for ln in lines):
            return "markdown"
        if "**" in text_preview or "```" in text_preview:
            return "markdown"
    except UnicodeDecodeError:
        return "text"

    # 4. python-magic (optional) — handles non-text or unusual MIME types
    fmt = _detect_via_magic(content)
    if fmt:
        return fmt

    return "text"


def _detect_via_magic(content: bytes) -> Optional[str]:
    """Try python-magic for MIME type detection. Returns None if unavailable."""
    try:
        from magic import detect_from_content  # type: ignore
        result = detect_from_content(content)
        mime = getattr(result, "mime_type", "") or ""
    except (ImportError, Exception):
        return None

    _MIME_MAP = {
        "application/pdf":                            "pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
        "application/msword":                         "docx",
        "text/html":                                  "html",
        "application/xhtml+xml":                      "html",
        "message/rfc822":                             "email",
        "text/markdown":                              "markdown",
        "text/x-markdown":                            "markdown",
        "text/plain":                                 "text",
    }
    return _MIME_MAP.get(mime)


def normalize_format(ext_or_tag: str) -> str:
    """Map a raw file extension or format tag to the canonical parser tag.

    e.g. ``"md"`` → ``"markdown"``, ``"eml"`` → ``"email"``, ``"markdown"`` → ``"markdown"``
    """
    key = ext_or_tag.lower().lstrip(".")
    return _EXT_TO_FORMAT.get(f".{key}", key)


def detect_encoding(content: bytes) -> str:
    """Detect the character encoding of text bytes. Defaults to utf-8."""
    try:
        import chardet  # type: ignore
        result = chardet.detect(content)
        enc = (result.get("encoding") or "utf-8").lower()
        # Normalise common aliases
        if enc in ("ascii", "us-ascii"):
            return "utf-8"
        return enc
    except ImportError:
        return "utf-8"
