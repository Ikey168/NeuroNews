"""Full-text article body extraction for blog posts.

Tries readability-lxml if installed; falls back to a bs4 heuristic that finds
the largest semantic content block (<article> / <main> / biggest <div>) and
strips navigation, scripts, and boilerplate.
"""

from __future__ import annotations

import re
from urllib.request import Request, urlopen

_USER_AGENT = "NeuroNewsBot/1.0 (+https://github.com/Ikey168/NeuroNews)"
_HTTP_TIMEOUT = 15

# Tags whose content is always boilerplate — strip before scoring.
_NOISE_TAGS = {
    "script", "style", "nav", "header", "footer", "aside",
    "form", "iframe", "button", "noscript", "figure", "figcaption",
}

# Minimum characters for full text to be considered useful.
_MIN_CHARS = 200


def fetch_full_text(url: str, _http_get=None) -> str:
    """Fetch ``url`` and extract the main readable text.

    Returns an empty string on any network or parse error so callers can
    fall back to the feed summary without crashing.
    """
    try:
        getter = _http_get or _default_http_get
        html = getter(url)
    except Exception:
        return ""

    if not html:
        return ""

    # Try readability-lxml first (much better extraction quality).
    try:
        from readability import Document as ReadabilityDoc  # type: ignore

        doc = ReadabilityDoc(html if isinstance(html, str) else html.decode("utf-8", errors="replace"))
        cleaned = doc.summary()
        text = _strip_tags(cleaned).strip()
        if len(text) >= _MIN_CHARS:
            return text
    except Exception:
        pass

    # bs4 fallback.
    try:
        return _bs4_extract(html if isinstance(html, bytes) else html.encode("utf-8"))
    except Exception:
        return ""


def _default_http_get(url: str) -> bytes:
    req = Request(
        url,
        headers={"User-Agent": _USER_AGENT, "Accept": "text/html,application/xhtml+xml,*/*"},
    )
    with urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
        return resp.read()


def _bs4_extract(html: bytes) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    # Remove noise elements in-place.
    for tag in soup.find_all(_NOISE_TAGS):
        tag.decompose()

    # Prefer semantic content containers.
    for selector in ("article", "main", '[role="main"]', ".post-content", ".entry-content", ".article-body"):
        el = soup.select_one(selector)
        if el:
            text = _normalize(el.get_text(separator=" "))
            if len(text) >= _MIN_CHARS:
                return text

    # Fall back to the largest <div> by text length (heuristic).
    best_text = ""
    for div in soup.find_all("div"):
        t = _normalize(div.get_text(separator=" "))
        if len(t) > len(best_text):
            best_text = t

    return best_text if len(best_text) >= _MIN_CHARS else ""


def _strip_tags(html: str) -> str:
    """Remove HTML tags from a string."""
    return re.sub(r"<[^>]+>", " ", html)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
