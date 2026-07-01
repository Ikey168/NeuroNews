"""
Coverage tests for src/argument_mining/metadata.py — actor/source metadata
extractor (issue #114).

These tests exercise the real public API (extract_actors, store_actors,
run_actor_batch) and internal helpers against the regex-fallback path, plus
the spaCy NER branch via a mocked pipeline.  spaCy's ``en_core_web_sm`` model is
not loaded in CI, so the default path is the regex fallback; the spaCy branches
are covered by patching ``_get_nlp`` where it is looked up.

All tests run fully offline — no DuckDB, no trained model, no network.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

# Ensure repo root is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import src.argument_mining.metadata as M
from src.argument_mining.metadata import (
    ActorRecord,
    _dedup,
    _entity_id,
    _from_authors,
    _ner_actors,
    _valid_name,
    extract_actors,
    run_actor_batch,
    store_actors,
)
from services.ingest.common.document_model import Document


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _doc(document_id, source_type, content="", **kw):
    return Document(
        document_id=document_id,
        source_type=source_type,
        language="en",
        ingested_at=0,
        content=content,
        **kw,
    )


def _roles(records):
    return {(r.actor_name, r.role) for r in records}


def _names(records):
    return {r.actor_name for r in records}


# ---------------------------------------------------------------------------
# entity id
# ---------------------------------------------------------------------------

def test_entity_id_is_deterministic_and_prefixed():
    a = _entity_id("Barack Obama")
    b = _entity_id("  barack   obama ")  # whitespace/case normalised
    assert a == b
    assert a.startswith("ent-")
    assert len(a) == len("ent-") + 12


def test_entity_id_differs_for_distinct_names():
    assert _entity_id("Alice") != _entity_id("Bob")


# ---------------------------------------------------------------------------
# _valid_name
# ---------------------------------------------------------------------------

def test_valid_name_accepts_capitalised_and_acronym():
    assert _valid_name("Jane Doe")
    assert _valid_name("WHO")


def test_valid_name_rejects_empty_short_skip_and_lowercase():
    assert not _valid_name("")
    assert not _valid_name("a")            # too short
    assert not _valid_name("the")          # in skip set
    assert not _valid_name("lowercase")    # first char not upper


# ---------------------------------------------------------------------------
# ActorRecord.make
# ---------------------------------------------------------------------------

def test_actor_record_make_sets_entity_id_and_timestamp():
    rec = ActorRecord.make("doc-1", "news", "Jane Doe", "author", 0.9)
    assert rec.document_id == "doc-1"
    assert rec.actor_name == "Jane Doe"
    assert rec.role == "author"
    assert rec.confidence == 0.9
    assert rec.entity_id == _entity_id("Jane Doe")
    assert isinstance(rec.extracted_at, str) and "T" in rec.extracted_at


def test_from_authors_filters_invalid_and_makes_records():
    recs = _from_authors("d", "news", ["Jane Doe", "", "the", "  "], role="author")
    assert _names(recs) == {"Jane Doe"}
    assert recs[0].confidence == 0.95
    assert recs[0].role == "author"


# ---------------------------------------------------------------------------
# _dedup
# ---------------------------------------------------------------------------

def test_dedup_keeps_highest_confidence_per_name_role():
    lo = ActorRecord.make("d", "news", "Jane", "speaker", 0.5)
    hi = ActorRecord.make("d", "news", "jane", "speaker", 0.9)  # same key (lowercased)
    other = ActorRecord.make("d", "news", "Jane", "author", 0.6)  # different role
    out = _dedup([lo, hi, other])
    by_key = {(r.actor_name.lower(), r.role): r for r in out}
    assert by_key[("jane", "speaker")].confidence == 0.9
    assert ("jane", "author") in by_key
    assert len(out) == 2


# ---------------------------------------------------------------------------
# _ner_actors — spaCy branch (mocked) + empty/None branches
# ---------------------------------------------------------------------------

def test_ner_actors_returns_empty_when_no_nlp(monkeypatch):
    monkeypatch.setattr(M, "_get_nlp", lambda: None)
    assert _ner_actors("Some text with Names") == []


def test_ner_actors_returns_empty_for_blank_text(monkeypatch):
    monkeypatch.setattr(M, "_get_nlp", lambda: object())  # nlp not None but text empty
    assert _ner_actors("") == []


def test_ner_actors_with_mocked_nlp_filters_labels_and_length():
    class _Ent:
        def __init__(self, text, label):
            self.text = text
            self.label_ = label

    class _Doc:
        ents = [
            _Ent("Barack Obama", "PERSON"),
            _Ent("Acme Corp", "ORG"),
            _Ent("Paris", "GPE"),
            _Ent("X", "PERSON"),        # too short -> dropped
            _Ent("A Number", "CARDINAL"),  # wrong label -> dropped
        ]

    def _fake_nlp(text):
        return _Doc()

    orig = M._get_nlp
    M._get_nlp = lambda: _fake_nlp
    try:
        pairs = _ner_actors("irrelevant body text")
    finally:
        M._get_nlp = orig
    labels = dict(pairs)
    assert labels.get("Barack Obama") == "PERSON"
    assert labels.get("Acme Corp") == "ORG"
    assert labels.get("Paris") == "GPE"
    assert "X" not in labels
    assert "A Number" not in labels


def test_ner_actors_swallows_pipeline_exception():
    def _boom(_text):
        raise RuntimeError("pipeline failed")

    orig = M._get_nlp
    M._get_nlp = lambda: _boom
    try:
        assert _ner_actors("text") == []
    finally:
        M._get_nlp = orig


# ---------------------------------------------------------------------------
# _get_nlp — real (spaCy model absent -> returns None, cached)
# ---------------------------------------------------------------------------

def test_get_nlp_returns_none_when_model_missing_and_caches(monkeypatch):
    # Reset the module-level cache so the load path executes once.
    monkeypatch.setattr(M, "_nlp", None, raising=False)
    monkeypatch.setattr(M, "_nlp_tried", False, raising=False)
    first = M._get_nlp()
    # In CI en_core_web_sm is not installed -> None. Second call hits the cache.
    second = M._get_nlp()
    assert first is second


# ---------------------------------------------------------------------------
# news / blog / web extractor (regex fallback path)
# ---------------------------------------------------------------------------

def test_extract_news_authors_outlet_and_speakers(monkeypatch):
    monkeypatch.setattr(M, "_get_nlp", lambda: None)  # force regex fallback
    doc = _doc(
        "n1", "news",
        content="Barack Obama said the policy would help millions of people.",
        source_id="Reuters",
        authors=["Jane Doe"],
    )
    recs = extract_actors(doc)
    keyed = _roles(recs)
    assert ("Jane Doe", "author") in keyed
    assert ("Reuters", "subject") in keyed          # outlet from source_id
    assert ("Barack Obama", "speaker") in keyed      # _SAID_RE match
    # confidences
    by_name = {r.actor_name: r for r in recs}
    assert by_name["Jane Doe"].confidence == 0.95
    assert by_name["Reuters"].confidence == 0.90


def test_extract_news_org_caps_subject(monkeypatch):
    monkeypatch.setattr(M, "_get_nlp", lambda: None)
    doc = _doc(
        "n2", "news",
        content="The International Monetary Fund said reforms are needed across Europe.",
    )
    recs = extract_actors(doc)
    # _ORG_CAPS_RE should capture an "... Fund" org as a low-confidence subject.
    assert any(r.role == "subject" and "Fund" in r.actor_name and r.confidence == 0.65
               for r in recs)


def test_extract_blog_uses_news_extractor(monkeypatch):
    monkeypatch.setattr(M, "_get_nlp", lambda: None)
    doc = _doc("bl1", "blog", content="Elon Musk said the rocket launched on schedule.",
               authors=["Blog Author"])
    recs = extract_actors(doc)
    assert ("Blog Author", "author") in _roles(recs)
    assert ("Elon Musk", "speaker") in _roles(recs)


def test_extract_news_spacy_branch(monkeypatch):
    # Force the spaCy branch by returning a truthy nlp and stubbing _ner_actors.
    monkeypatch.setattr(M, "_get_nlp", lambda: object())
    monkeypatch.setattr(
        M, "_ner_actors",
        lambda text: [("Angela Merkel", "PERSON"), ("Acme Corp", "ORG")],
    )
    doc = _doc("n3", "news", content="Body text here about several topics.")
    recs = extract_actors(doc)
    by_name = {r.actor_name: r for r in recs}
    assert by_name["Angela Merkel"].role == "speaker"
    assert by_name["Angela Merkel"].confidence == 0.82
    assert by_name["Acme Corp"].role == "subject"
    assert by_name["Acme Corp"].confidence == 0.75


# ---------------------------------------------------------------------------
# paper extractor
# ---------------------------------------------------------------------------

def test_extract_paper_authors_institution_and_publisher(monkeypatch):
    monkeypatch.setattr(M, "_get_nlp", lambda: None)
    doc = _doc(
        "p1", "paper",
        content="The experiment was conducted at Cambridge University with strong results.",
        authors=["Alan Turing"],
        metadata={"publisher": "Nature Publishing", "journal": "Science Journal"},
    )
    recs = extract_actors(doc)
    keyed = _roles(recs)
    assert ("Alan Turing", "author") in keyed
    assert ("Nature Publishing", "subject") in keyed
    assert any(r.role == "subject" and "Cambridge" in r.actor_name for r in recs)


def test_extract_paper_journal_fallback_when_no_publisher(monkeypatch):
    monkeypatch.setattr(M, "_get_nlp", lambda: None)
    doc = _doc("p2", "paper", content="Findings summarised.",
               metadata={"journal": "Journal Of Testing"})
    recs = extract_actors(doc)
    assert ("Journal Of Testing", "subject") in _roles(recs)


def test_extract_paper_spacy_branch(monkeypatch):
    monkeypatch.setattr(M, "_get_nlp", lambda: object())
    monkeypatch.setattr(M, "_ner_actors", lambda text: [("Marie Curie", "PERSON")])
    doc = _doc("p3", "paper", content="Some research body.")
    recs = extract_actors(doc)
    assert "Marie Curie" in _names(recs)


# ---------------------------------------------------------------------------
# transcript extractor
# ---------------------------------------------------------------------------

def test_extract_transcript_segments_speakers_and_labels(monkeypatch):
    monkeypatch.setattr(M, "_get_nlp", lambda: None)
    doc = _doc(
        "t1", "transcript",
        content="Alice Smith: Welcome to the show today everyone here.\n"
                "Bob Jones: Thanks so much for having me here today.",
        authors=["Host Person"],
        metadata={
            "segments": [{"speaker": "Carol White"}, {"label": "Dan Brown"}],
            "speakers": [{"name": "Eve Black"}, "Frank Green"],
        },
    )
    recs = extract_actors(doc)
    names = _names(recs)
    assert "Host Person" in names
    assert {"Carol White", "Dan Brown"} <= names       # segment speakers/labels
    assert {"Eve Black", "Frank Green"} <= names        # speakers list dict+str
    assert {"Alice Smith", "Bob Jones"} <= names        # body-text labels
    by_name = {r.actor_name: r for r in recs}
    assert by_name["Carol White"].confidence == 0.90
    assert by_name["Alice Smith"].confidence == 0.80


def test_extract_transcript_dedups_repeated_speaker(monkeypatch):
    monkeypatch.setattr(M, "_get_nlp", lambda: None)
    doc = _doc(
        "t2", "transcript",
        content="Carol White: first line long enough to be kept here.",
        metadata={"segments": [{"speaker": "Carol White"}],
                  "speakers": ["Carol White"]},
    )
    recs = extract_actors(doc)
    speakers = [r for r in recs if r.actor_name == "Carol White"]
    assert len(speakers) == 1  # not duplicated across segment/speakers/body


def test_extract_transcript_spacy_subjects(monkeypatch):
    monkeypatch.setattr(M, "_get_nlp", lambda: object())
    monkeypatch.setattr(M, "_ner_actors", lambda text: [("United Nations", "ORG")])
    doc = _doc("t3", "transcript", content="Discussion about global affairs today.")
    recs = extract_actors(doc)
    assert "United Nations" in _names(recs)


# ---------------------------------------------------------------------------
# book extractor
# ---------------------------------------------------------------------------

def test_extract_book_dialogue_speakers_and_publisher(monkeypatch):
    monkeypatch.setattr(M, "_get_nlp", lambda: None)
    doc = _doc(
        "b1", "book",
        content="WINSTON: I understand the situation now completely.\n"
                "JULIA: We really must be careful about all this.",
        authors=["George Orwell"],
        metadata={"publisher": "Penguin Books"},
    )
    recs = extract_actors(doc)
    keyed = _roles(recs)
    assert ("George Orwell", "author") in keyed
    assert ("Penguin Books", "subject") in keyed
    # ALL-CAPS labels get title-cased to speakers.
    assert ("Winston", "speaker") in keyed
    assert ("Julia", "speaker") in keyed


def test_extract_book_spacy_subjects(monkeypatch):
    monkeypatch.setattr(M, "_get_nlp", lambda: object())
    monkeypatch.setattr(M, "_ner_actors", lambda text: [("London", "GPE")])
    doc = _doc("b2", "book", content="A story set somewhere interesting.")
    recs = extract_actors(doc)
    assert "London" in _names(recs)


# ---------------------------------------------------------------------------
# note / upload extractor
# ---------------------------------------------------------------------------

def test_extract_note_creator(monkeypatch):
    monkeypatch.setattr(M, "_get_nlp", lambda: None)
    doc = _doc("no1", "note", content="Some meeting notes about the deadline.",
               metadata={"creator": "Sam Wilson"})
    recs = extract_actors(doc)
    keyed = _roles(recs)
    assert ("Sam Wilson", "author") in keyed
    assert next(r for r in recs if r.actor_name == "Sam Wilson").confidence == 0.92


def test_extract_note_uploader_fallback_key(monkeypatch):
    monkeypatch.setattr(M, "_get_nlp", lambda: None)
    doc = _doc("no2", "note", content="notes",
               metadata={"uploaded_by": "Pat Lee"})
    recs = extract_actors(doc)
    assert ("Pat Lee", "author") in _roles(recs)


def test_extract_note_spacy_subjects(monkeypatch):
    monkeypatch.setattr(M, "_get_nlp", lambda: object())
    monkeypatch.setattr(M, "_ner_actors", lambda text: [("Globex", "ORG")])
    doc = _doc("no3", "note", content="Notes referencing an organisation.",
               metadata={})
    recs = extract_actors(doc)
    assert "Globex" in _names(recs)


# ---------------------------------------------------------------------------
# extract_actors dispatch / default fallback
# ---------------------------------------------------------------------------

def test_extract_actors_unknown_source_type_uses_news_default(monkeypatch):
    monkeypatch.setattr(M, "_get_nlp", lambda: None)
    doc = _doc("w1", "web", content="Tim Cook said the product would ship soon.",
               authors=["Web Writer"])
    recs = extract_actors(doc)
    assert ("Web Writer", "author") in _roles(recs)
    assert ("Tim Cook", "speaker") in _roles(recs)


# ---------------------------------------------------------------------------
# store_actors — fake connection captures SQL params
# ---------------------------------------------------------------------------

class _FakeConn:
    def __init__(self):
        self.calls = []
        self.rows = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return self

    def fetchall(self):
        return self.rows


def test_store_actors_persists_each_record():
    recs = [
        ActorRecord.make("d", "news", "Jane Doe", "author", 0.95),
        ActorRecord.make("d", "news", "Reuters", "subject", 0.90),
    ]
    conn = _FakeConn()
    store_actors(recs, conn)
    assert len(conn.calls) == 2
    # First param row carries the record fields in order.
    _sql, params = conn.calls[0]
    assert params[0] == "d"           # document_id
    assert params[2] == "Jane Doe"    # actor_name
    assert params[4] == "author"      # role


# ---------------------------------------------------------------------------
# run_actor_batch
# ---------------------------------------------------------------------------

class _BatchConn:
    """Fake DuckDB-like connection for run_actor_batch."""

    def __init__(self, rows):
        self._rows = rows
        self.stored = []
        self._mode = None

    def execute(self, sql, params=None):
        if "SELECT" in sql:
            self._mode = "select"
        else:
            self._mode = "insert"
            self.stored.append(params)
        return self

    def fetchall(self):
        return self._rows


def test_run_actor_batch_processes_rows_and_stores(monkeypatch):
    monkeypatch.setattr(M, "_get_nlp", lambda: None)
    rows = [
        ("art-1", "Headline", "Barack Obama said the plan will proceed as expected.",
         "Reuters", "news"),
        ("art-2", "Empty", None, "AP", "news"),
    ]
    conn = _BatchConn(rows)
    lock = threading.Lock()
    result = run_actor_batch(conn, lock, limit=10)
    assert result["processed"] == 2
    assert result["skipped"] == 0
    assert result["actors"] >= 1        # at least Barack Obama from art-1
    assert conn.stored, "expected at least one INSERT call"


def test_run_actor_batch_returns_error_dict_on_query_failure():
    class _BadConn:
        def execute(self, *a, **k):
            raise RuntimeError("db down")

    result = run_actor_batch(_BadConn(), threading.Lock(), limit=5)
    assert result["processed"] == 0
    assert result["actors"] == 0
    assert result["skipped"] == 0
    assert "db down" in result["error"]


def test_run_actor_batch_skips_document_that_raises(monkeypatch):
    monkeypatch.setattr(M, "_get_nlp", lambda: None)
    # Make extract_actors raise for every doc so the per-row except path runs.
    monkeypatch.setattr(
        M, "extract_actors",
        lambda doc: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    rows = [("art-1", "T", "Some content here that is long enough.", "src", "news")]
    conn = _BatchConn(rows)
    result = run_actor_batch(conn, threading.Lock(), limit=5)
    assert result["processed"] == 0
    assert result["skipped"] == 1
