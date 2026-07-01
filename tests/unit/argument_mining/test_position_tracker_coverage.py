"""
Coverage tests for src/argument_mining/position_tracker.py — position
follow-through tracker (issue #111).

Exercises the real public API (check_position_followthrough,
store_followthrough, run_followthrough_batch) and the internal signal
classifiers / helpers.  Fully offline — no DuckDB, no network.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

# Ensure repo root is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import src.argument_mining.position_tracker as PT
from src.argument_mining.position_tracker import (
    FollowthroughRecord,
    _actor_mentioned,
    _classify_sentence,
    _split_sentences,
    _topic_keywords,
    _topic_mentioned,
    _update_id,
    check_position_followthrough,
    run_followthrough_batch,
    store_followthrough,
)


# ---------------------------------------------------------------------------
# _update_id
# ---------------------------------------------------------------------------

def test_update_id_deterministic_and_prefixed():
    a = _update_id("pos-1", "art-1")
    b = _update_id("pos-1", "art-1")
    assert a == b
    assert a.startswith("upd-")


def test_update_id_differs_by_article():
    assert _update_id("pos-1", "art-1") != _update_id("pos-1", "art-2")


# ---------------------------------------------------------------------------
# _split_sentences
# ---------------------------------------------------------------------------

def test_split_sentences_drops_short_fragments():
    text = "Short. This is a sufficiently long sentence to be retained here."
    out = _split_sentences(text)
    assert out == ["This is a sufficiently long sentence to be retained here."]


def test_split_sentences_on_paragraph_breaks():
    text = "First paragraph long enough to count as a real sentence.\n\n" \
           "Second paragraph also long enough to be a real sentence."
    out = _split_sentences(text)
    assert len(out) == 2


# ---------------------------------------------------------------------------
# _actor_mentioned
# ---------------------------------------------------------------------------

def test_actor_mentioned_matches_long_word():
    assert _actor_mentioned("Joe Biden announced the plan.", "Joe Biden")
    assert not _actor_mentioned("The rocket launched today.", "Joe Biden")


def test_actor_mentioned_short_actor_uses_full_string():
    # No word >= 4 chars -> falls back to whole-string containment.
    assert _actor_mentioned("The EU met in Brussels.", "EU")
    assert not _actor_mentioned("The council met.", "EU")


# ---------------------------------------------------------------------------
# _topic_mentioned / _topic_keywords
# ---------------------------------------------------------------------------

def test_topic_mentioned_true_and_false():
    kw = _topic_keywords("environment")
    assert _topic_mentioned("carbon emissions are rising", kw)
    assert not _topic_mentioned("a story about football matches", kw)


def test_topic_keywords_known_label_returns_taxonomy_set():
    kw = _topic_keywords("environment")
    assert "carbon" in kw
    assert "climate" in kw


def test_topic_keywords_unknown_label_falls_back_to_label():
    kw = _topic_keywords("Blockchain")
    assert kw == frozenset({"blockchain"})


# ---------------------------------------------------------------------------
# _classify_sentence — all branches
# ---------------------------------------------------------------------------

def test_classify_reversal():
    assert _classify_sentence("The minister reversed the carbon pledge.") == ("reversed", 0.80)


def test_classify_reaffirm():
    assert _classify_sentence("The minister reaffirmed the carbon pledge.") == ("reaffirmed", 0.75)


def test_classify_mixed_signals_is_updated():
    out = _classify_sentence("The minister reaffirmed but then reversed the plan.")
    assert out == ("updated", 0.50)


def test_classify_update_only():
    assert _classify_sentence("The minister modified the carbon plan.") == ("updated", 0.65)


def test_classify_no_signal():
    assert _classify_sentence("The minister spoke about carbon at the summit.") == ("no_signal", 0.30)


# ---------------------------------------------------------------------------
# check_position_followthrough
# ---------------------------------------------------------------------------

def _articles():
    return [
        ("a1",
         "President Biden reaffirmed his carbon emission pledge today. "
         "He said renewable energy remains a national priority for climate.",
         "2024-02-01"),
        ("a2", "A totally unrelated story about football and weather.", "2024-02-01"),
        ("a3",
         "Biden reversed course on the carbon plan and dropped renewable targets now.",
         "2024-03-01"),
        ("a4", "", "2024-01-01"),  # empty content -> skipped
    ]


def test_check_followthrough_classifies_relevant_articles():
    recs = check_position_followthrough("pos-1", "Joe Biden", "environment", _articles())
    by_article = {r.article_id: r for r in recs}
    # a2 (no actor/topic) and a4 (empty) are excluded.
    assert set(by_article) == {"a1", "a3"}
    assert by_article["a1"].update_type == "reaffirmed"
    assert by_article["a1"].confidence == 0.75
    assert by_article["a3"].update_type == "reversed"
    assert by_article["a3"].confidence == 0.80
    for r in recs:
        assert r.position_id == "pos-1"
        assert r.update_id == _update_id("pos-1", r.article_id)
        assert r.evidence_text  # non-empty
        assert len(r.evidence_text) <= 500


def test_check_followthrough_no_signal_when_mentioned_but_neutral():
    articles = [
        ("a1",
         "Joe Biden discussed carbon and renewable energy at a climate conference. "
         "He met other leaders to talk about environmental cooperation and solar.",
         "2024-02-01"),
    ]
    recs = check_position_followthrough("pos-2", "Joe Biden", "environment", articles)
    assert len(recs) == 1
    assert recs[0].update_type == "no_signal"
    assert recs[0].confidence == 0.30


def test_check_followthrough_skips_when_topic_absent():
    articles = [
        ("a1", "Joe Biden gave a speech about football and sports today at length.", "2024-02-01"),
    ]
    recs = check_position_followthrough("pos-3", "Joe Biden", "environment", articles)
    assert recs == []


def test_check_followthrough_uses_content_prefix_when_no_actor_sentence():
    # Actor appears in content (so article passes the gate) but not in any
    # individual >=20-char sentence -> best_sent stays "" -> content prefix used.
    articles = [
        ("a1",
         "Carbon emissions and renewable energy remain vital issues for the planet. "
         "Biden.",
         "2024-02-01"),
    ]
    recs = check_position_followthrough("pos-4", "Biden", "environment", articles)
    assert len(recs) == 1
    assert recs[0].update_type == "no_signal"
    assert recs[0].evidence_text.startswith("Carbon emissions")


# ---------------------------------------------------------------------------
# store_followthrough
# ---------------------------------------------------------------------------

class _FakeConn:
    def __init__(self):
        self.executemany_calls = []

    def executemany(self, sql, seq):
        self.executemany_calls.append((sql, list(seq)))


def test_store_followthrough_noop_on_empty():
    conn = _FakeConn()
    store_followthrough([], conn)
    assert conn.executemany_calls == []


def test_store_followthrough_persists_records():
    rec = FollowthroughRecord(
        update_id="upd-1",
        position_id="pos-1",
        article_id="a1",
        update_type="reversed",
        evidence_text="Biden reversed the plan.",
        confidence=0.80,
        detected_at="2024-03-01T00:00:00+00:00",
    )
    conn = _FakeConn()
    store_followthrough([rec], conn)
    assert len(conn.executemany_calls) == 1
    _sql, rows = conn.executemany_calls[0]
    assert rows[0][0] == "upd-1"
    assert rows[0][3] == "reversed"


# ---------------------------------------------------------------------------
# run_followthrough_batch
# ---------------------------------------------------------------------------

class _BatchConn:
    """Fake connection returning positions then articles for each position."""

    def __init__(self, positions, articles):
        self._positions = positions
        self._articles = articles
        self._next = None
        self.stored = []

    def execute(self, sql, params=None):
        if "policy_positions" in sql:
            self._next = "positions"
        elif "news_articles" in sql:
            self._next = "articles"
        else:
            self._next = "insert"
            self.stored.append(params)
        return self

    def executemany(self, sql, seq):
        self.stored.append(list(seq))
        return self

    def fetchall(self):
        if self._next == "positions":
            return self._positions
        if self._next == "articles":
            return self._articles
        return []


def test_run_followthrough_batch_counts_and_stores():
    positions = [
        ("pos-1", "Joe Biden", "environment", "2024-01-01T00:00:00+00:00"),
    ]
    articles = [
        ("a1",
         "President Biden reaffirmed his carbon emission pledge on renewable energy today.",
         "2024-02-01"),
        ("a3",
         "Biden reversed course on the carbon plan and dropped renewable targets now.",
         "2024-03-01"),
    ]
    conn = _BatchConn(positions, articles)
    counts = run_followthrough_batch(conn, threading.Lock(), limit=10)
    assert counts["checked"] == 1
    assert counts["matched"] == 2   # both articles matched
    assert counts["stored"] == 2
    assert conn.stored, "expected persisted rows"


def test_run_followthrough_batch_no_articles_continues():
    positions = [("pos-1", "Joe Biden", "environment", "2024-01-01T00:00:00+00:00")]
    conn = _BatchConn(positions, [])  # no articles
    counts = run_followthrough_batch(conn, threading.Lock(), limit=10)
    assert counts["checked"] == 1
    assert counts["matched"] == 0
    assert counts["stored"] == 0


def test_run_followthrough_batch_matched_but_no_records():
    # Articles exist but none reference the actor+topic -> check returns [].
    positions = [("pos-1", "Joe Biden", "environment", None)]  # None extracted_at
    articles = [("a1", "Unrelated story about football matches and the weather.", "2024-02-01")]
    conn = _BatchConn(positions, articles)
    counts = run_followthrough_batch(conn, threading.Lock(), limit=5)
    assert counts["checked"] == 1
    assert counts["matched"] == 0
    assert counts["stored"] == 0


def test_run_followthrough_batch_empty_positions():
    conn = _BatchConn([], [])
    counts = run_followthrough_batch(conn, threading.Lock(), limit=5)
    assert counts == {"checked": 0, "matched": 0, "stored": 0}
