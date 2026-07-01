"""
Coverage-focused unit tests for src/argument_mining/attribution.py.

Targets the previously-uncovered per-type classifier branches
(_news / _paper / _transcript / _blog_note), the public classify_attribution
dispatch + snippet handling, and the run_attribution_batch DuckDB sweep
including its error handlers.

All assertions are real behavioural checks against the module's public and
internal API.  No network, no trained model.
"""
from __future__ import annotations

import threading

import pytest

from src.argument_mining.attribution import (
    _blog_note,
    _news,
    _paper,
    _transcript,
    classify_attribution,
    run_attribution_batch,
)

duckdb = pytest.importorskip("duckdb")


# ---------------------------------------------------------------------------
# _news
# ---------------------------------------------------------------------------

class TestNewsClassifier:
    def test_according_to_extracts_source(self):
        attributed, snippet = _news("According to Reuters, the plant closed.")
        assert attributed is True
        assert snippet == "Reuters"

    def test_per_source(self):
        attributed, snippet = _news("Per the report, sales grew last year.")
        assert attributed is True
        assert snippet == "the report"

    def test_citing_source(self):
        attributed, snippet = _news("Citing internal memos, the paper reported changes.")
        assert attributed is True
        assert snippet == "internal memos"

    def test_officials_say_pattern(self):
        attributed, snippet = _news("Officials said the road was closed for repairs.")
        assert attributed is True
        assert snippet.lower() == "officials"

    def test_named_speaker_said(self):
        attributed, snippet = _news("John Smith said the deal was completed on Friday.")
        assert attributed is True
        assert snippet == "John Smith"

    def test_said_rejected_for_generic_opener(self):
        # snippet "The government" starts with "the " -> rejected as real attribution
        attributed, snippet = _news("The government said nothing new about the matter.")
        assert attributed is False
        assert snippet is None

    def test_no_attribution_returns_false(self):
        attributed, snippet = _news("The unemployment rate fell to 3.8 percent in March.")
        assert attributed is False
        assert snippet is None


# ---------------------------------------------------------------------------
# _paper
# ---------------------------------------------------------------------------

class TestPaperClassifier:
    def test_apa_parenthetical(self):
        attributed, snippet = _paper("The result held (Smith et al., 2023) across all trials.")
        assert attributed is True
        assert snippet == "(Smith et al., 2023)"

    def test_numeric_inline_citation(self):
        attributed, snippet = _paper("This effect was demonstrated earlier [12,13].")
        assert attributed is True
        assert snippet == "[12,13]"

    def test_paren_numeric_citation(self):
        attributed, snippet = _paper("Prior work established the mechanism (1).")
        assert attributed is True
        assert snippet == "(1)"

    def test_no_citation(self):
        attributed, snippet = _paper("The cohort comprised three thousand participants.")
        assert attributed is False
        assert snippet is None


# ---------------------------------------------------------------------------
# _transcript
# ---------------------------------------------------------------------------

class TestTranscriptClassifier:
    def test_speaker_label(self):
        attributed, snippet = _transcript("Jane Doe: welcome to today's session.")
        assert attributed is True
        assert snippet == "Jane Doe"

    def test_said_that_attribution(self):
        attributed, snippet = _transcript("The minister said that the plan works well.")
        assert attributed is True
        assert snippet == "The minister"

    def test_falls_through_to_news(self):
        # No label / no "said that" -> falls back to news patterns
        attributed, snippet = _transcript("According to the chair, the vote passed.")
        assert attributed is True
        assert snippet == "the chair"

    def test_transcript_no_attribution(self):
        attributed, snippet = _transcript("The weather was pleasant throughout the afternoon.")
        assert attributed is False
        assert snippet is None


# ---------------------------------------------------------------------------
# _blog_note
# ---------------------------------------------------------------------------

class TestBlogNoteClassifier:
    def test_first_person_anchor(self):
        attributed, snippet = _blog_note("I found a clear 30% drop in signups over the month.")
        assert attributed is True
        assert snippet == "I found"

    def test_we_observed_anchor(self):
        attributed, snippet = _blog_note("We observed a consistent regression in the benchmark suite.")
        assert attributed is True
        assert snippet.lower().startswith("we observed")

    def test_in_my_experience_anchor(self):
        attributed, snippet = _blog_note("In my experience the tool degrades under heavy load.")
        assert attributed is True
        assert "my experience" in snippet.lower()

    def test_opinion_as_fact_is_unsourced(self):
        # opinion-as-fact marker WITHOUT first-person anchor -> not attributed
        attributed, snippet = _blog_note("Obviously this is the best framework available today.")
        assert attributed is False
        assert snippet is None

    def test_blog_falls_through_to_news(self):
        attributed, snippet = _blog_note("According to the vendor, delivery is guaranteed.")
        assert attributed is True
        assert snippet == "the vendor"


# ---------------------------------------------------------------------------
# classify_attribution public dispatch
# ---------------------------------------------------------------------------

class TestClassifyAttribution:
    def test_dispatch_news(self):
        attributed, snippet = classify_attribution(
            "According to the ministry, output rose.", "news"
        )
        assert attributed is True
        assert snippet == "the ministry"

    def test_dispatch_paper(self):
        attributed, snippet = classify_attribution(
            "The finding replicated (Jones, 2021).", "paper"
        )
        assert attributed is True
        assert snippet == "(Jones, 2021)"

    def test_dispatch_book_uses_paper_rules(self):
        # book maps to the paper classifier
        attributed, snippet = classify_attribution(
            "The event is documented [4].", "book"
        )
        assert attributed is True
        assert snippet == "[4]"

    def test_dispatch_transcript(self):
        attributed, snippet = classify_attribution(
            "Bob Jones: thanks for having me.", "transcript"
        )
        assert attributed is True
        assert snippet == "Bob Jones"

    def test_dispatch_blog(self):
        attributed, snippet = classify_attribution(
            "I measured a 12% latency improvement.", "blog"
        )
        assert attributed is True
        assert snippet == "I measured"

    def test_dispatch_note_uses_blog_rules(self):
        attributed, snippet = classify_attribution(
            "Obviously we should ship it now.", "note"
        )
        # "we should" is not one of the first-person verbs; opinion marker present
        assert attributed is False
        assert snippet is None

    def test_web_maps_to_news(self):
        attributed, snippet = classify_attribution(
            "According to the site, uptime improved.", "web"
        )
        assert attributed is True
        assert snippet == "the site"

    def test_unknown_source_type_defaults_to_news(self):
        attributed, snippet = classify_attribution(
            "According to officials, the alert was lifted.", "unknown-type"
        )
        assert attributed is True
        assert snippet == "officials"

    def test_no_attribution_yields_none(self):
        attributed, snippet = classify_attribution(
            "The bridge collapsed at dawn on Tuesday.", "news"
        )
        assert attributed is False
        assert snippet is None


# ---------------------------------------------------------------------------
# run_attribution_batch
# ---------------------------------------------------------------------------

def _make_claims_conn():
    conn = duckdb.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE argument_claims (
            claim_id VARCHAR PRIMARY KEY,
            claim_text VARCHAR,
            source_type VARCHAR,
            attributed BOOLEAN,
            attribution_text VARCHAR
        )
        """
    )
    return conn


class TestRunAttributionBatch:
    def test_updates_null_rows(self):
        conn = _make_claims_conn()
        conn.execute(
            "INSERT INTO argument_claims VALUES (?,?,?,?,?)",
            ["c1", "According to Reuters, sales rose.", "news", None, None],
        )
        conn.execute(
            "INSERT INTO argument_claims VALUES (?,?,?,?,?)",
            ["c2", "The cat sat quietly on the mat.", "news", None, None],
        )
        result = run_attribution_batch(conn, threading.Lock(), limit=10)
        assert result == {"updated": 2, "skipped": 0}

        rows = conn.execute(
            "SELECT claim_id, attributed, attribution_text FROM argument_claims ORDER BY claim_id"
        ).fetchall()
        by_id = {r[0]: (r[1], r[2]) for r in rows}
        assert by_id["c1"] == (True, "Reuters")
        assert by_id["c2"] == (False, None)

    def test_already_classified_rows_are_not_selected(self):
        conn = _make_claims_conn()
        # attributed already set -> WHERE attributed IS NULL excludes it
        conn.execute(
            "INSERT INTO argument_claims VALUES (?,?,?,?,?)",
            ["done", "According to X, y.", "news", True, "X"],
        )
        result = run_attribution_batch(conn, threading.Lock(), limit=10)
        assert result == {"updated": 0, "skipped": 0}

    def test_null_text_and_source_defaults(self):
        conn = _make_claims_conn()
        conn.execute(
            "INSERT INTO argument_claims VALUES (?,?,?,?,?)",
            ["c-null", None, None, None, None],
        )
        result = run_attribution_batch(conn, threading.Lock(), limit=10)
        assert result["updated"] == 1
        row = conn.execute(
            "SELECT attributed FROM argument_claims WHERE claim_id = 'c-null'"
        ).fetchone()
        # empty text classified with default 'news' -> not attributed
        assert row[0] is False

    def test_query_error_returns_error_dict(self):
        class BadConn:
            def execute(self, *args, **kwargs):
                raise RuntimeError("boom")

        result = run_attribution_batch(BadConn(), threading.Lock(), limit=5)
        assert result["updated"] == 0
        assert result["skipped"] == 0
        assert result["error"] == "boom"

    def test_per_row_update_error_counts_as_skipped(self):
        conn = _make_claims_conn()
        conn.execute(
            "INSERT INTO argument_claims VALUES (?,?,?,?,?)",
            ["c1", "According to Reuters, sales rose.", "news", None, None],
        )

        real_execute = conn.execute
        state = {"select_done": False}

        class WrapConn:
            def execute(self, sql, *args, **kwargs):
                # allow the SELECT sweep, then make every UPDATE fail
                if sql.strip().upper().startswith("UPDATE"):
                    raise RuntimeError("update failed")
                return real_execute(sql, *args, **kwargs)

        result = run_attribution_batch(WrapConn(), threading.Lock(), limit=10)
        # SELECT returned 1 row, UPDATE failed -> updated 0, skipped 1
        assert result == {"updated": 0, "skipped": 1}
