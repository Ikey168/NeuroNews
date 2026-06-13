"""Comprehensive tests for services/rag/normalization.py."""

import os
import sys
from datetime import datetime

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

pytest.importorskip("bs4")

from services.rag.normalization import ArticleNormalizer, normalize_article  # noqa: E402


@pytest.fixture
def norm():
    # disable language detection for deterministic results
    return ArticleNormalizer(detect_language=False)


class TestInit:
    def test_defaults(self):
        n = ArticleNormalizer()
        assert n.preserve_paragraphs is True
        assert n.min_paragraph_length == 10

    def test_custom(self):
        n = ArticleNormalizer(detect_language=False, min_paragraph_length=5)
        assert n.detect_language is False
        assert n.min_paragraph_length == 5


class TestIsHtml:
    def test_html(self, norm):
        assert norm._is_html("<p>hello</p>") is True

    def test_plain(self, norm):
        assert norm._is_html("just plain text") is False


class TestCleanText:
    def test_removes_urls_and_emails(self, norm):
        cleaned = norm._clean_text("Visit https://example.com or mail a@b.com today")
        assert "example.com" not in cleaned
        assert "a@b.com" not in cleaned
        assert "Visit" in cleaned

    def test_normalizes_whitespace(self, norm):
        # \s+ collapses all runs of whitespace (including newlines) to a space
        assert norm._clean_text("a    b\n\n\n  c") == "a b c"

    def test_empty(self, norm):
        assert norm._clean_text("") == ""


class TestParseDatetime:
    @pytest.mark.parametrize("inp,year", [
        ("2026-01-15T10:30:00", 2026),
        ("2026-01-15", 2026),
        ("January 15, 2026", 2026),
        ("01/15/2026", 2026),
    ])
    def test_formats(self, norm, inp, year):
        result = norm._parse_datetime(inp)
        assert isinstance(result, datetime)
        assert result.year == year

    def test_unparseable(self, norm):
        assert norm._parse_datetime("not a date") is None


class TestNormalizeText:
    def test_plain_text_title_extraction(self, norm):
        # short single-line text without a trailing period becomes the title
        result = norm.normalize_article("Breaking News Today")
        assert result["title"] == "Breaking News Today"
        assert result["char_count"] >= 0

    def test_empty_content(self, norm):
        result = norm.normalize_article("")
        assert result["content"] == ""
        assert result["word_count"] == 0
        assert result["language"] == "unknown"

    def test_whitespace_only(self, norm):
        result = norm.normalize_article("   \n  \n  ")
        assert result["content"] == ""


class TestNormalizeHtml:
    def test_extracts_title_and_content(self, norm):
        html = """
        <html><head><title>My Headline</title></head>
        <body>
          <script>ignore()</script>
          <p>This is the main article body content with several words here.</p>
        </body></html>
        """
        result = norm.normalize_article(html)
        assert result["title"] == "My Headline"
        assert "main article body" in result["content"]
        assert "ignore" not in result["content"]  # script removed

    def test_canonical_url_extracted(self, norm):
        html = """
        <html><head><link rel="canonical" href="https://news.example.com/a"/></head>
        <body><h1>Title</h1><p>Body text content for the article here.</p></body></html>
        """
        result = norm.normalize_article(html)
        assert result["url"] == "https://news.example.com/a"


class TestMetadataOverride:
    def test_metadata_overrides_extracted(self, norm):
        result = norm.normalize_article(
            "Some Title\nbody text here",
            metadata={"title": "Override Title", "url": "https://x.com/1"},
        )
        assert result["title"] == "Override Title"
        assert result["url"] == "https://x.com/1"
        assert result["metadata"]["title"] == "Override Title"


class TestPostProcessUrlValidation:
    def test_invalid_url_cleared(self, norm):
        result = norm.normalize_article(
            "Title\nbody", metadata={"url": "not-a-valid-url"}
        )
        assert result["url"] == ""


class TestConvenienceFunction:
    def test_normalize_article_function(self):
        result = normalize_article("Headline body text", detect_language=False)
        assert result["title"] == "Headline body text"
        assert isinstance(result, dict)
