"""
Reference (citation) providers.

arXiv metadata does not include a paper's reference list, so references that
become CITES edges are sourced separately. The default provider talks to a
Semantic-Scholar-style API (HTTP injectable); a static provider is handy for
tests and offline ingestion.
"""

from __future__ import annotations

import json
from typing import Callable, List, Optional

from src.ingestion.connectors.paper.models import PaperMetadata, Reference

HttpGet = Callable[[str], bytes]


class ReferencesProvider:
    """Interface: given a paper, return the works it cites."""

    def references_for(self, paper: PaperMetadata) -> List[Reference]:
        raise NotImplementedError


class StaticReferencesProvider(ReferencesProvider):
    """Returns references from an in-memory map keyed by document id."""

    def __init__(self, by_document_id: Optional[dict] = None):
        self._by_id = by_document_id or {}

    def references_for(self, paper: PaperMetadata) -> List[Reference]:
        return list(self._by_id.get(paper.document_id, []))


def parse_s2_references(payload: bytes | str | dict) -> List[Reference]:
    """Parse a Semantic Scholar ``/paper/{id}/references`` response."""
    if isinstance(payload, (bytes, str)):
        data = json.loads(payload)
    else:
        data = payload

    references: List[Reference] = []
    for item in data.get("data", []):
        cited = item.get("citedPaper") or {}
        external = cited.get("externalIds") or {}
        references.append(
            Reference(
                title=cited.get("title"),
                arxiv_id=external.get("ArXiv"),
                doi=external.get("DOI"),
                year=cited.get("year"),
            )
        )
    return references


class SemanticScholarReferences(ReferencesProvider):
    """Fetches references from the Semantic Scholar Graph API."""

    API = "https://api.semanticscholar.org/graph/v1"

    def __init__(self, http_get: Optional[HttpGet] = None, api_url: Optional[str] = None):
        self._http_get = http_get or self._default_http_get
        self._api_url = api_url or self.API

    @staticmethod
    def _default_http_get(url: str) -> bytes:
        from urllib.request import Request, urlopen

        req = Request(url, headers={"User-Agent": "NeuroNewsBot/1.0"})
        with urlopen(req, timeout=20) as resp:
            return resp.read()

    def references_for(self, paper: PaperMetadata) -> List[Reference]:
        if paper.arxiv_id:
            key = f"arXiv:{paper.arxiv_id}"
        elif paper.doi:
            key = f"DOI:{paper.doi}"
        else:
            return []
        fields = "title,year,externalIds"
        url = f"{self._api_url}/paper/{key}/references?fields={fields}&limit=1000"
        return parse_s2_references(self._http_get(url))
