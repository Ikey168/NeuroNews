"""Coverage tests for src/reports/generate_report.py.

Uses a REAL in-memory DuckDB connection seeded with a ``news_articles`` table,
patched in where ``generate_report`` looks up ``get_shared_connection`` /
``_LOCK`` (both imported inside the functions from
``src.database.local_analytics_connector``). PDF paths require fpdf2 and are
guarded with pytest.importorskip.
"""
from __future__ import annotations

import csv
import io
import sys
import threading
import types
from datetime import datetime, timedelta, timezone

import pytest

import src.reports.generate_report as gr


# ---------------------------------------------------------------------------
# Fake fpdf so the _render_pdf body runs even when fpdf2 is not installed.
# This exercises the real branching in generate_report (font/colour/paging
# decisions) without requiring the optional dependency.
# ---------------------------------------------------------------------------

class _FakeFPDF:
    def __init__(self):
        self._y = 10.0
        self.calls = []

    def set_auto_page_break(self, *a, **k):
        self.calls.append(("auto_page_break", a, k))

    def add_page(self):
        self._y = 10.0
        self.calls.append(("add_page",))

    def set_font(self, *a, **k):
        self.calls.append(("set_font", a))

    def set_text_color(self, *a):
        self.calls.append(("text_color", a))

    def set_draw_color(self, *a):
        pass

    def set_line_width(self, *a):
        pass

    def cell(self, w, h, txt="", ln=False, *a, **k):
        # Advance y when a line break is requested to mimic layout flow.
        if ln:
            self._y += h
        self.calls.append(("cell", txt))

    def ln(self, h=0):
        self._y += h

    def line(self, *a):
        pass

    def get_y(self):
        return self._y

    def output(self):
        return b"%PDF-1.4 fake pdf body\n%%EOF"


@pytest.fixture
def fake_fpdf(monkeypatch):
    """Install a fake ``fpdf`` module exposing FPDF."""
    mod = types.ModuleType("fpdf")
    mod.FPDF = _FakeFPDF
    monkeypatch.setitem(sys.modules, "fpdf", mod)
    return mod


# ---------------------------------------------------------------------------
# Real DuckDB fixture seeded with articles
# ---------------------------------------------------------------------------

def _make_seeded_conn():
    import duckdb

    conn = duckdb.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE news_articles (
            id            VARCHAR,
            title         VARCHAR,
            url           VARCHAR,
            content       VARCHAR,
            publish_date  TIMESTAMP,
            source        VARCHAR,
            category      VARCHAR,
            sentiment_score DOUBLE,
            sentiment_label VARCHAR
        )
        """
    )
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = [
        # id, title, url, content, publish_date, source, category, score, label
        ("a1", "Nvidia announces new GPU", "http://ex/1", "c1",
         now - timedelta(days=1), "Reuters", "Technology", 0.8, "positive"),
        ("a2", "Nvidia stock climbs", "http://ex/2", "c2",
         now - timedelta(days=2), "Reuters", "Business", 0.5, "positive"),
        ("a3", "Concerns over Nvidia supply", "", "c3",
         now - timedelta(days=3), "Bloomberg", "Technology", -0.6, "negative"),
        ("a4", "Market steady on chips", "http://ex/4", "c4",
         now - timedelta(days=4), "AP", "Business", 0.0, "neutral"),
        # An article outside the last_24_hours window and unrelated topic
        ("a5", "Weather report calm", "http://ex/5", "c5",
         now - timedelta(days=40), "AP", "Weather", 0.1, "neutral"),
    ]
    conn.executemany(
        "INSERT INTO news_articles VALUES (?,?,?,?,?,?,?,?,?)", rows
    )
    return conn


@pytest.fixture
def duck(monkeypatch):
    """Patch get_shared_connection / _LOCK in the connector module."""
    conn = _make_seeded_conn()
    lock = threading.Lock()
    import src.database.local_analytics_connector as connmod

    monkeypatch.setattr(connmod, "get_shared_connection", lambda: conn)
    monkeypatch.setattr(connmod, "_LOCK", lock)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Period helpers
# ---------------------------------------------------------------------------

def test_period_to_cutoff_known():
    cutoff = gr._period_to_cutoff("last_7_days")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    delta = now - cutoff
    # ~7 days, allow a little slack
    assert timedelta(days=6, hours=23) < delta < timedelta(days=7, hours=1)


def test_period_to_cutoff_unknown_raises():
    with pytest.raises(ValueError, match="Unknown period"):
        gr._period_to_cutoff("last_5_minutes")


# ---------------------------------------------------------------------------
# _fetch_report_data
# ---------------------------------------------------------------------------

def test_fetch_report_data_computes_stats(duck):
    data = gr._fetch_report_data("Nvidia", "last_7_days")
    assert data.topic == "Nvidia"
    assert data.period == "last_7_days"
    # a1, a2, a3 match "Nvidia" in title within 7 days
    assert data.total_articles == 3
    titles = {a.title for a in data.articles}
    assert "Nvidia announces new GPU" in titles
    # 2 positive out of 3
    assert data.positive_pct == round(2 / 3 * 100, 1)
    assert data.negative_pct == round(1 / 3 * 100, 1)
    assert data.neutral_pct == 0.0
    # avg of 0.8, 0.5, -0.6 = 0.7/3
    assert data.avg_sentiment == round((0.8 + 0.5 - 0.6) / 3, 4)
    # Reuters appears twice -> first top source
    assert data.top_sources[0] == "Reuters"
    assert "UTC" in data.generated_at
    # url COALESCE default kept empty string for a3
    a3 = next(a for a in data.articles if a.article_id == "a3")
    assert a3.url == ""


def test_fetch_report_data_empty_result(duck):
    data = gr._fetch_report_data("NoSuchTopicXYZ", "last_7_days")
    assert data.total_articles == 0
    assert data.avg_sentiment == 0.0
    assert data.positive_pct == 0.0
    assert data.neutral_pct == 0.0
    assert data.top_sources == []
    assert data.articles == []


def test_fetch_report_data_category_match(duck):
    # "Technology" matches via category ILIKE even though title lacks the word
    data = gr._fetch_report_data("Technology", "last_30_days")
    ids = {a.article_id for a in data.articles}
    assert {"a1", "a3"}.issubset(ids)


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

def test_generate_csv_header_and_rows(duck):
    raw = gr.generate_csv("Nvidia", "last_7_days")
    assert isinstance(raw, bytes)
    text = raw.decode("utf-8")
    reader = list(csv.reader(io.StringIO(text)))
    header = reader[0]
    assert header == [
        "article_id", "title", "source", "category",
        "publish_date", "sentiment_label", "sentiment_score", "url",
    ]
    # 3 matching articles + header
    assert len(reader) == 4
    body_ids = {r[0] for r in reader[1:]}
    assert body_ids == {"a1", "a2", "a3"}


def test_generate_csv_empty(duck):
    raw = gr.generate_csv("NoSuchTopicXYZ", "last_7_days")
    reader = list(csv.reader(io.StringIO(raw.decode("utf-8"))))
    assert len(reader) == 1  # header only


# ---------------------------------------------------------------------------
# _latin1 sanitiser
# ---------------------------------------------------------------------------

def test_latin1_substitutes_smart_punctuation():
    out = gr._latin1("‘hi’ “there” — …")
    assert out == "'hi' \"there\" - ..."


def test_latin1_replaces_unencodable():
    # Emoji is outside latin-1; errors='replace' -> '?'
    out = gr._latin1("emoji \U0001F600 end")
    assert "?" in out
    assert out.startswith("emoji ")


# ---------------------------------------------------------------------------
# PDF (requires fpdf2)
# ---------------------------------------------------------------------------

def test_generate_pdf_bytes(duck):
    pytest.importorskip("fpdf")
    raw = gr.generate_pdf("Nvidia", "last_7_days")
    assert isinstance(raw, bytes)
    assert raw[:4] == b"%PDF"
    assert len(raw) > 500


def test_generate_pdf_empty_topic(duck):
    pytest.importorskip("fpdf")
    raw = gr.generate_pdf("NoSuchTopicXYZ", "last_7_days")
    assert raw[:4] == b"%PDF"


def test_render_pdf_missing_dependency(monkeypatch, duck):
    """Force the ImportError branch in _render_pdf."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "fpdf":
            raise ImportError("no fpdf")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    data = gr._fetch_report_data("Nvidia", "last_7_days")
    with pytest.raises(RuntimeError, match="fpdf2 is required"):
        gr._render_pdf(data)


def test_generate_pdf_with_fake(duck, fake_fpdf):
    """Cover generate_pdf + _render_pdf body using the injected fake fpdf."""
    raw = gr.generate_pdf("Nvidia", "last_7_days")
    assert raw == b"%PDF-1.4 fake pdf body\n%%EOF"


def test_generate_custom_pdf_with_fake(duck, fake_fpdf):
    f = gr.CustomReportFilter(keywords=["Nvidia"], period="last_30_days")
    raw = gr.generate_custom_pdf(f)
    assert raw.startswith(b"%PDF")


def test_render_pdf_paging_with_fake(duck, fake_fpdf):
    """Force the get_y() > 265 add_page() branch and title truncation."""
    articles = [
        gr.ArticleRow(
            article_id=f"x{i}",
            title=("Very long headline " * 10),  # >90 chars -> truncated
            source="SourceX",
            category="Cat",
            publish_date="2026-01-01 00:00",
            sentiment_label="positive" if i % 2 else "negative",
            sentiment_score=0.3,
            url="http://ex",
        )
        for i in range(80)  # each cell(ln=True) advances y -> triggers add_page
    ]
    data = gr.ReportData(
        topic="Paging",
        period="last_7_days",
        generated_at="2026-01-01 00:00 UTC",
        total_articles=len(articles),
        avg_sentiment=0.3,
        positive_pct=50.0,
        negative_pct=50.0,
        neutral_pct=0.0,
        top_sources=["SourceX"],
        articles=articles,
    )
    raw = gr._render_pdf(data)
    assert raw.startswith(b"%PDF")


def test_render_pdf_unknown_sentiment_color_with_fake(duck, fake_fpdf):
    """An unknown sentiment label falls back to the default colour tuple."""
    data = gr.ReportData(
        topic="X", period="last_7_days", generated_at="now",
        total_articles=1, avg_sentiment=0.0,
        positive_pct=0.0, negative_pct=0.0, neutral_pct=100.0,
        top_sources=[],
        articles=[gr.ArticleRow("id1", "Title", "Src", "Cat", "2026-01-01 00:00",
                                 "mystery_label", 0.0, "http://x")],
    )
    raw = gr._render_pdf(data)
    assert raw.startswith(b"%PDF")


def test_cli_pdf_with_fake(duck, fake_fpdf, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        ["prog", "--topic", "Nvidia", "--period", "last_7_days",
         "--format", "pdf", "--out", str(tmp_path)],
    )
    gr._cli()
    pdfs = list(tmp_path.glob("*.pdf"))
    assert len(pdfs) == 1
    assert pdfs[0].read_bytes().startswith(b"%PDF")


def test_render_pdf_long_title_and_paging(duck):
    """Exercise title truncation and multi-page path in _render_pdf."""
    pytest.importorskip("fpdf")
    articles = [
        gr.ArticleRow(
            article_id=f"x{i}",
            title=("Very long headline " * 10),  # >90 chars -> truncated
            source="SourceX",
            category="Cat",
            publish_date="2026-01-01 00:00",
            sentiment_label="positive" if i % 2 else "negative",
            sentiment_score=0.3,
            url="http://ex",
        )
        for i in range(60)  # enough rows to trigger add_page()
    ]
    data = gr.ReportData(
        topic="Paging",
        period="last_7_days",
        generated_at="2026-01-01 00:00 UTC",
        total_articles=len(articles),
        avg_sentiment=0.3,
        positive_pct=50.0,
        negative_pct=50.0,
        neutral_pct=0.0,
        top_sources=["SourceX"],
        articles=articles,
    )
    raw = gr._render_pdf(data)
    assert raw[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# CustomReportFilter + _resolve_date_range
# ---------------------------------------------------------------------------

def test_resolve_date_range_period_default():
    f = gr.CustomReportFilter(keywords=["AI"])
    dt_from, dt_to = gr._resolve_date_range(f)
    assert dt_to > dt_from
    assert (dt_to - dt_from) >= timedelta(days=6)


def test_resolve_date_range_explicit_period():
    f = gr.CustomReportFilter(keywords=["AI"], period="last_30_days")
    dt_from, dt_to = gr._resolve_date_range(f)
    assert (dt_to - dt_from) >= timedelta(days=29)


def test_resolve_date_range_unknown_period():
    f = gr.CustomReportFilter(keywords=["AI"], period="never")
    with pytest.raises(ValueError, match="Unknown period"):
        gr._resolve_date_range(f)


def test_resolve_date_range_explicit_dates():
    f = gr.CustomReportFilter(keywords=["AI"], date_from="2026-01-01", date_to="2026-02-01")
    dt_from, dt_to = gr._resolve_date_range(f)
    assert dt_from == datetime(2026, 1, 1)
    assert dt_to == datetime(2026, 2, 1)


def test_resolve_date_range_only_from():
    f = gr.CustomReportFilter(keywords=["AI"], date_from="2026-01-01")
    dt_from, dt_to = gr._resolve_date_range(f)
    assert dt_from == datetime(2026, 1, 1)
    # date_to defaults to now
    assert dt_to > dt_from


def test_resolve_date_range_only_to():
    f = gr.CustomReportFilter(keywords=["AI"], date_to="2030-01-01")
    dt_from, dt_to = gr._resolve_date_range(f)
    # date_from defaults to 2000-01-01
    assert dt_from == datetime(2000, 1, 1)
    assert dt_to == datetime(2030, 1, 1)


def test_resolve_date_range_bad_date():
    f = gr.CustomReportFilter(keywords=["AI"], date_from="not-a-date")
    with pytest.raises(ValueError, match="Invalid date format"):
        gr._resolve_date_range(f)


# ---------------------------------------------------------------------------
# _build_custom_query
# ---------------------------------------------------------------------------

def test_build_custom_query_all_filters():
    f = gr.CustomReportFilter(
        keywords=["Nvidia", "chip"],
        period="last_30_days",
        sentiment="positive",
        sentiment_min=-0.5,
        sentiment_max=0.9,
        source="Reuters",
        category="Technology",
        limit=50,
    )
    sql, params = gr._build_custom_query(f)
    assert "news_articles" in sql
    assert "LIMIT 50" in sql
    assert "sentiment_label = ?" in sql
    assert "sentiment_score >= ?" in sql
    assert "sentiment_score <= ?" in sql
    assert "source ILIKE ?" in sql
    assert "category ILIKE ?" in sql
    # two keyword clauses -> 4 keyword params, plus 2 dates, 1 sentiment,
    # 2 score bounds, source, category
    assert "%Nvidia%" in params and "Reuters" in params and "Technology" in params
    assert "positive" in params


def test_build_custom_query_no_keywords():
    f = gr.CustomReportFilter(keywords=[], sentiment="all")
    sql, params = gr._build_custom_query(f)
    # sentiment 'all' skipped, no keyword clause
    assert "sentiment_label = ?" not in sql
    # date conditions always present
    assert "publish_date >= ?" in sql


# ---------------------------------------------------------------------------
# fetch_custom_report_data
# ---------------------------------------------------------------------------

def test_fetch_custom_report_data_basic(duck):
    f = gr.CustomReportFilter(keywords=["Nvidia"], period="last_30_days")
    data = gr.fetch_custom_report_data(f)
    assert data.total_articles == 3
    assert data.topic == "Nvidia"  # derived from keywords
    assert data.period == "last_30_days"
    assert data.top_sources[0] == "Reuters"


def test_fetch_custom_report_data_title_and_sentiment_filter(duck):
    f = gr.CustomReportFilter(
        keywords=["Nvidia"],
        period="last_30_days",
        sentiment="positive",
        report_title="My Positive Report",
    )
    data = gr.fetch_custom_report_data(f)
    assert data.topic == "My Positive Report"
    assert all(a.sentiment_label == "positive" for a in data.articles)
    assert data.total_articles == 2


def test_fetch_custom_report_data_date_range_period_label(duck):
    f = gr.CustomReportFilter(keywords=["Nvidia"], date_from="2000-01-01", date_to="2100-01-01")
    data = gr.fetch_custom_report_data(f)
    assert "2000-01-01 to 2100-01-01" == data.period
    # picks up all Nvidia articles (a1,a2,a3)
    assert data.total_articles == 3


def test_fetch_custom_report_data_empty(duck):
    f = gr.CustomReportFilter(keywords=["ZZZNoMatch"], period="last_7_days")
    data = gr.fetch_custom_report_data(f)
    assert data.total_articles == 0
    assert data.avg_sentiment == 0.0
    assert data.positive_pct == 0.0


# ---------------------------------------------------------------------------
# Custom CSV / PDF
# ---------------------------------------------------------------------------

def test_generate_custom_csv(duck):
    f = gr.CustomReportFilter(keywords=["Nvidia"], period="last_30_days")
    raw = gr.generate_custom_csv(f)
    reader = list(csv.reader(io.StringIO(raw.decode("utf-8"))))
    assert reader[0][0] == "article_id"
    assert len(reader) == 4  # header + 3


def test_generate_custom_pdf(duck):
    pytest.importorskip("fpdf")
    f = gr.CustomReportFilter(keywords=["Nvidia"], period="last_30_days")
    raw = gr.generate_custom_pdf(f)
    assert raw[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def test_cli_csv_only(duck, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv",
        ["prog", "--topic", "Nvidia", "--period", "last_7_days",
         "--format", "csv", "--out", str(tmp_path)],
    )
    gr._cli()
    out_files = list(tmp_path.glob("*.csv"))
    assert len(out_files) == 1
    assert out_files[0].name == "report_nvidia_last_7_days.csv"
    text = out_files[0].read_text()
    assert "article_id" in text
    captured = capsys.readouterr()
    assert "CSV" in captured.out


def test_cli_both_formats(duck, tmp_path, monkeypatch, capsys):
    pytest.importorskip("fpdf")
    monkeypatch.setattr(
        "sys.argv",
        ["prog", "--topic", "Nvidia AI", "--period", "last_7_days",
         "--format", "both", "--out", str(tmp_path)],
    )
    gr._cli()
    assert (tmp_path / "report_nvidia_ai_last_7_days.csv").exists()
    assert (tmp_path / "report_nvidia_ai_last_7_days.pdf").exists()
    pdf_bytes = (tmp_path / "report_nvidia_ai_last_7_days.pdf").read_bytes()
    assert pdf_bytes[:4] == b"%PDF"
    captured = capsys.readouterr()
    assert "PDF" in captured.out


def test_cli_pdf_only(duck, tmp_path, monkeypatch):
    pytest.importorskip("fpdf")
    monkeypatch.setattr(
        "sys.argv",
        ["prog", "--topic", "Nvidia", "--period", "last_7_days",
         "--format", "pdf", "--out", str(tmp_path)],
    )
    gr._cli()
    pdfs = list(tmp_path.glob("*.pdf"))
    assert len(pdfs) == 1
    assert not list(tmp_path.glob("*.csv"))
