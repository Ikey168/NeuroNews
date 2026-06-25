"""
Data models for the books connector: book metadata and section hierarchy.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import List, Optional


def book_id(isbn: Optional[str] = None, title: Optional[str] = None, file_path: Optional[str] = None) -> str:
    """Stable document id for a book section, preferring ISBN, then title, then file path."""
    if isbn:
        return f"isbn:{isbn}"
    key = (title or file_path or "").strip().lower()
    digest = hashlib.md5(key.encode()).hexdigest()[:12]
    return f"book:{digest}"


def section_id(book_doc_id: str, path: List[str]) -> str:
    """Stable id for a section within a book."""
    fragment = "/".join(p.lower().replace(" ", "-") for p in path if p)
    return f"{book_doc_id}#{fragment}"


@dataclass
class BookSection:
    """A node in a book's structural hierarchy (part / chapter / section)."""

    title: str
    text: str = ""
    level: int = 0  # 0 = part, 1 = chapter, 2 = section, 3+ = subsection
    children: List["BookSection"] = field(default_factory=list)

    def path_from(self, ancestors: List[str]) -> List[str]:
        return ancestors + ([self.title] if self.title else [])

    def all_sections(self, ancestors: Optional[List[str]] = None) -> List[tuple]:
        """Flatten the tree into (path, text) pairs (DFS, skips empty bodies)."""
        ancestors = ancestors or []
        path = self.path_from(ancestors)
        result = []
        if self.text.strip():
            result.append((path, self.text))
        for child in self.children:
            result.extend(child.all_sections(path))
        return result


@dataclass
class BookMetadata:
    """Normalized metadata for a book."""

    title: str
    authors: List[str] = field(default_factory=list)
    language: str = "en"
    isbn: Optional[str] = None
    publisher: Optional[str] = None
    published_year: Optional[int] = None
    description: Optional[str] = None
    file_path: Optional[str] = None
    format: str = "unknown"  # "epub" | "pdf"
    sections: List[BookSection] = field(default_factory=list)
    extractor: str = "none"

    @property
    def document_id(self) -> str:
        return book_id(self.isbn, self.title, self.file_path)
