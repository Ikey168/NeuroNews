"""Comprehensive tests for services/rag/filters.py."""

import os
import sys
from datetime import date, datetime

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.rag.filters import (  # noqa: E402
    FilterCriteria,
    FilterType,
    RAGFiltersService,
    create_filters_service,
)


@pytest.fixture
def svc():
    return RAGFiltersService()


class TestFilterType:
    def test_values(self):
        assert FilterType.LANGUAGE.value == "language"
        assert FilterType.DATE_RANGE.value == "date_range"


class TestParseFilterParams:
    def test_language_string(self, svc):
        c = svc.parse_filter_params(lang="EN")
        assert c.languages == {"en"}

    def test_language_list(self, svc):
        c = svc.parse_filter_params(language=["EN", "De"])
        assert c.languages == {"en", "de"}

    def test_dates(self, svc):
        c = svc.parse_filter_params(date_from="2026-01-01", date_to="2026-02-01")
        assert c.date_from == date(2026, 1, 1)
        assert c.date_to == date(2026, 2, 1)

    def test_sources_and_exclusions(self, svc):
        c = svc.parse_filter_params(sources=["a", "b"], exclude_domains="spam.com")
        assert c.sources == {"a", "b"}
        assert c.exclude_domains == {"spam.com"}

    def test_publishers_domains(self, svc):
        c = svc.parse_filter_params(publisher="NYT", domain=["x.com", "y.com"])
        assert c.publishers == {"NYT"}
        assert c.domains == {"x.com", "y.com"}

    def test_empty(self, svc):
        c = svc.parse_filter_params()
        assert c.languages is None
        assert c.date_from is None


class TestParseDate:
    @pytest.mark.parametrize("inp,expected", [
        ("2026-01-15", date(2026, 1, 15)),
        ("2026/01/15", date(2026, 1, 15)),
        ("15-01-2026", date(2026, 1, 15)),
        ("2026-01-15T10:30:00Z", date(2026, 1, 15)),
    ])
    def test_string_formats(self, svc, inp, expected):
        assert svc._parse_date(inp) == expected

    def test_date_passthrough(self, svc):
        d = date(2026, 5, 5)
        assert svc._parse_date(d) == d

    def test_datetime_to_date(self, svc):
        assert svc._parse_date(datetime(2026, 5, 5, 12, 0)) == date(2026, 5, 5)

    def test_none_and_invalid(self, svc):
        assert svc._parse_date(None) is None
        assert svc._parse_date("not-a-date") is None


class TestParseStringSet:
    def test_string(self, svc):
        assert svc._parse_string_set("x") == {"x"}

    def test_list_filters_empty(self, svc):
        assert svc._parse_string_set(["a", "", "b"]) == {"a", "b"}

    def test_other(self, svc):
        assert svc._parse_string_set(5) == {"5"}
        assert svc._parse_string_set(None) == set()


class TestExtractors:
    def test_extract_language_fields(self, svc):
        assert svc._extract_language({"language": "EN"}) == "en"
        assert svc._extract_language({"metadata": {"lang": "DE"}}) == "de"
        assert svc._extract_language({}) is None

    def test_extract_date(self, svc):
        assert svc._extract_date({"published_date": "2026-01-10"}) == date(2026, 1, 10)
        assert svc._extract_date({}) is None

    def test_extract_source(self, svc):
        assert svc._extract_source({"source": "BBC"}) == "BBC"

    def test_extract_domain_direct(self, svc):
        assert svc._extract_domain({"domain": "x.com"}) == "x.com"

    def test_extract_domain_from_url(self, svc):
        assert svc._extract_domain({"url": "https://News.Example.com/a"}) == "news.example.com"

    def test_extract_domain_none(self, svc):
        assert svc._extract_domain({}) is None


class TestApplyFilters:
    def docs(self):
        return [
            {"id": 1, "language": "en", "published_date": "2026-01-10",
             "source": "BBC", "domain": "bbc.com"},
            {"id": 2, "language": "de", "published_date": "2026-03-10",
             "source": "Spiegel", "domain": "spiegel.de"},
            {"id": 3, "language": "en", "published_date": "2025-06-10",
             "source": "CNN", "domain": "cnn.com"},
        ]

    def test_empty_documents(self, svc):
        assert svc.apply_filters([], FilterCriteria()) == []

    def test_no_criteria_passes_all(self, svc):
        docs = self.docs()
        assert len(svc.apply_filters(docs, FilterCriteria())) == 3

    def test_language_filter(self, svc):
        c = svc.parse_filter_params(lang="en")
        result = svc.apply_filters(self.docs(), c)
        assert {d["id"] for d in result} == {1, 3}

    def test_date_range_filter(self, svc):
        c = svc.parse_filter_params(date_from="2026-01-01", date_to="2026-02-01")
        result = svc.apply_filters(self.docs(), c)
        assert {d["id"] for d in result} == {1}

    def test_source_filter(self, svc):
        c = svc.parse_filter_params(sources=["BBC", "CNN"])
        result = svc.apply_filters(self.docs(), c)
        assert {d["id"] for d in result} == {1, 3}

    def test_exclude_domain(self, svc):
        c = svc.parse_filter_params(exclude_domains="spiegel.de")
        result = svc.apply_filters(self.docs(), c)
        assert 2 not in {d["id"] for d in result}


class TestFactoryAndSummary:
    def test_factory(self):
        assert isinstance(create_filters_service(), RAGFiltersService)

    def test_criteria_summary(self, svc):
        c = svc.parse_filter_params(lang="en", sources=["a"], date_from="2026-01-01")
        summary = svc._criteria_summary(c)
        assert "lang" in summary
        assert "sources" in summary

    def test_criteria_summary_empty(self, svc):
        assert svc._criteria_summary(FilterCriteria()) == "no filters"
