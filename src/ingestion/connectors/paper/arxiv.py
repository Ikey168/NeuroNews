"""
arXiv discovery and metadata parsing.

Fetches paper metadata from the arXiv Atom API and parses it into
``PaperMetadata``. The HTTP layer is injectable so callers (and tests) can
supply recorded responses instead of hitting the network.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Callable, List, Optional
import xml.etree.ElementTree as ET

from src.ingestion.connectors.paper.models import PaperMetadata

_ATOM = "{http://www.w3.org/2005/Atom}"
_ARXIV = "{http://arxiv.org/schemas/atom}"

ARXIV_API = "http://export.arxiv.org/api/query"
USER_AGENT = "NeuroNewsBot/1.0 (+https://github.com/Ikey168/NeuroNews)"
HTTP_TIMEOUT = 20

HttpGet = Callable[[str], bytes]


def _default_http_get(url: str) -> bytes:
    from urllib.request import Request, urlopen

    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return resp.read()


def _strip_version(arxiv_id: str) -> str:
    """Drop a trailing version suffix, e.g. ``1706.03762v7`` -> ``1706.03762``."""
    return re.sub(r"v\d+$", "", arxiv_id.strip())


def _parse_date(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def parse_atom(xml_bytes: bytes) -> List[PaperMetadata]:
    """Parse an arXiv Atom API response into one PaperMetadata per entry."""
    root = ET.fromstring(xml_bytes)
    papers: List[PaperMetadata] = []

    for entry in root.findall(f"{_ATOM}entry"):
        raw_id = (entry.findtext(f"{_ATOM}id") or "").strip()
        arxiv_id = None
        if "/abs/" in raw_id:
            arxiv_id = _strip_version(raw_id.rsplit("/abs/", 1)[1])

        title = re.sub(r"\s+", " ", (entry.findtext(f"{_ATOM}title") or "").strip())
        abstract = re.sub(r"\s+", " ", (entry.findtext(f"{_ATOM}summary") or "").strip())
        authors = [
            (a.findtext(f"{_ATOM}name") or "").strip()
            for a in entry.findall(f"{_ATOM}author")
            if (a.findtext(f"{_ATOM}name") or "").strip()
        ]

        doi = entry.findtext(f"{_ARXIV}doi")
        primary_el = entry.find(f"{_ARXIV}primary_category")
        primary_category = primary_el.get("term") if primary_el is not None else None
        categories = [
            c.get("term") for c in entry.findall(f"{_ATOM}category") if c.get("term")
        ]

        pdf_url = None
        for link in entry.findall(f"{_ATOM}link"):
            if link.get("type") == "application/pdf" or link.get("title") == "pdf":
                pdf_url = link.get("href")
                break

        papers.append(
            PaperMetadata(
                title=title,
                arxiv_id=arxiv_id,
                doi=doi.strip() if doi else None,
                authors=authors,
                abstract=abstract,
                categories=categories,
                primary_category=primary_category,
                published=_parse_date(entry.findtext(f"{_ATOM}published")),
                pdf_url=pdf_url,
            )
        )
    return papers


class ArxivClient:
    """Thin client for fetching arXiv metadata by id."""

    def __init__(self, http_get: Optional[HttpGet] = None, api_url: str = ARXIV_API):
        self._http_get = http_get or _default_http_get
        self._api_url = api_url

    def fetch_by_id(self, arxiv_id: str) -> bytes:
        url = f"{self._api_url}?id_list={_strip_version(arxiv_id)}&max_results=1"
        return self._http_get(url)

    def get_metadata(self, arxiv_id: str) -> PaperMetadata:
        papers = parse_atom(self.fetch_by_id(arxiv_id))
        if not papers:
            raise ValueError(f"No arXiv entry found for {arxiv_id!r}")
        return papers[0]
