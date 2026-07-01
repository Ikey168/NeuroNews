"""Comprehensive coverage tests for src/database/local_warehouse_views.py.

These tests exercise the real view-derivation functions against a real
*in-memory* DuckDB connection seeded with controlled article rows. The only
thing mocked is the process-wide DuckDB connection factory
(``get_shared_connection``) -- which is patched *where it is looked up* inside
``local_analytics_connector`` -- so ``LocalAnalyticsConnector.execute_query``
runs actual SQL against our in-memory table. Every assertion checks the real
shape / values of the returned rows.
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

duckdb = pytest.importorskip("duckdb")

import src.database.local_analytics_connector as connector_mod  # noqa: E402
import src.database.local_warehouse_views as views  # noqa: E402


# --------------------------------------------------------------------------- #
# Fixtures: real in-memory DuckDB seeded with deterministic articles
# --------------------------------------------------------------------------- #

_NEWS_SCHEMA = """
CREATE TABLE news_articles (
    id            VARCHAR,
    title         VARCHAR,
    content       VARCHAR,
    publish_date  TIMESTAMP,
    source        VARCHAR,
    category      VARCHAR,
    sentiment_score DOUBLE,
    sentiment_label VARCHAR
);
"""


def _seed_rows(conn, rows):
    conn.execute(_NEWS_SCHEMA)
    conn.executemany(
        """
        INSERT INTO news_articles
        (id, title, content, publish_date, source, category,
         sentiment_score, sentiment_label)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def _make_rows():
    """Build a small but realistic corpus with clear entity/topic structure."""
    now = datetime.now()
    recent = now - timedelta(hours=2)      # within the 24h "recent" window
    stale = now - timedelta(days=3)        # older than 24h
    rows = [
        # Three closely-related "Jerome Powell / Fed" articles -> a cluster.
        ("a1", "Jerome Powell signals Federal Reserve rate cut",
         "Jerome Powell said the Federal Reserve may cut interest rates soon amid inflation cooling.",
         recent, "Reuters", "Business", 0.4, "positive"),
        ("a2", "Powell defends Federal Reserve policy on inflation",
         "Powell told lawmakers the Federal Reserve will hold rates. Inflation remains a concern for Powell.",
         recent, "Bloomberg", "Business", -0.2, "negative"),
        ("a3", "Federal Reserve minutes show Powell divided on inflation",
         "The Federal Reserve minutes reveal Powell and colleagues debating inflation and interest rates.",
         stale, "AP", "Business", 0.05, "neutral"),
        # Two Ukraine / Russia articles -> a place cluster.
        ("b1", "Ukraine reports strikes near Kyiv as Russia advances",
         "Ukraine officials said Russia launched strikes near Kyiv overnight targeting infrastructure.",
         recent, "BBC", "World", -0.6, "negative"),
        ("b2", "Russia and Ukraine trade blame over Kyiv attacks",
         "Russia denied targeting civilians in Ukraine while Kyiv reported casualties.",
         stale, "Reuters", "World", -0.5, "negative"),
        # A standalone tech article -> singleton-ish cluster.
        ("c1", "Nvidia unveils new AI chip for data centers",
         "Nvidia announced a new AI accelerator chip aimed at data center customers and cloud providers.",
         stale, "TechCrunch", "Technology", 0.7, "positive"),
    ]
    return rows


@pytest.fixture
def duck_conn(monkeypatch):
    """Patch the shared-connection factory with a real in-memory DuckDB."""
    conn = duckdb.connect(":memory:")
    _seed_rows(conn, _make_rows())
    # Patch where LocalAnalyticsConnector.execute_query looks it up.
    monkeypatch.setattr(connector_mod, "get_shared_connection", lambda: conn)
    yield conn
    conn.close()


@pytest.fixture
def empty_conn(monkeypatch):
    """Patched connection with an empty news_articles table."""
    conn = duckdb.connect(":memory:")
    conn.execute(_NEWS_SCHEMA)
    monkeypatch.setattr(connector_mod, "get_shared_connection", lambda: conn)
    yield conn
    conn.close()


def run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# Pure helper functions
# --------------------------------------------------------------------------- #

def test_normalize_token_strips_possessive_and_punct():
    assert views._normalize_token("Powell's") == "powell"
    assert views._normalize_token("-AI&") == "ai"
    assert views._normalize_token("Reserve") == "reserve"


def test_terms_filters_stopwords_and_short_tokens():
    terms = views._terms("The Federal Reserve is on a go")
    # stopwords ("the", "is", "on", "a", "go") and short tokens dropped.
    assert "federal" in terms
    assert "reserve" in terms
    assert "the" not in terms
    assert "is" not in terms
    # single/dual char tokens excluded (length must be > 2)
    assert all(len(t) > 2 for t in terms)


def test_terms_empty_input():
    assert views._terms("") == []
    assert views._terms(None) == []


def test_max_cluster_articles_env(monkeypatch):
    monkeypatch.setenv("NEURONEWS_CLUSTER_MAX_ARTICLES", "500")
    assert views._max_cluster_articles() == 500
    # floor at 100
    monkeypatch.setenv("NEURONEWS_CLUSTER_MAX_ARTICLES", "10")
    assert views._max_cluster_articles() == 100
    # invalid -> default 3000
    monkeypatch.setenv("NEURONEWS_CLUSTER_MAX_ARTICLES", "not-a-number")
    assert views._max_cluster_articles() == 3000


def test_union_find_connects_components():
    uf = views._UnionFind(5)
    uf.union(0, 1)
    uf.union(1, 2)
    uf.union(3, 4)
    assert uf.find(0) == uf.find(2)
    assert uf.find(3) == uf.find(4)
    assert uf.find(0) != uf.find(3)


def test_label_for_thresholds():
    assert views._label_for(0.5) == "positive"
    assert views._label_for(-0.5) == "negative"
    assert views._label_for(0.0) == "neutral"
    assert views._label_for(0.05) == "neutral"  # boundary, not > 0.05


def test_extract_entities_strips_leading_trailing_filler():
    ents = views._extract_entities("As Israel warns, Jerome Powell speaks")
    # "As" is filler and stripped; the person survives.
    assert any(e == "Jerome Powell" for e in ents)
    # "As Israel" -> "Israel"
    assert "Israel" in ents


def test_extract_entities_acronyms_and_stopword_only():
    ents = views._extract_entities("The OPEC and NATO met with the EU")
    assert "OPEC" in ents
    assert "NATO" in ents
    assert "EU" in ents
    # A phrase made entirely of stopwords / sentence starters yields nothing.
    assert views._extract_entities("The This That") == []


def test_entity_type_classification():
    assert views._entity_type("Ukraine") == "place"
    assert views._entity_type("AI") == "topic"
    assert views._entity_type("Nvidia") == "org"
    assert views._entity_type("OPEC") == "org"          # all-caps acronym
    assert views._entity_type("Jerome Powell") == "person"
    assert views._entity_type("Federal Reserve") == "org"  # org keyword "reserve"
    assert views._entity_type("Solo") == "topic"        # single unknown word


def test_event_type_from_recent_fraction():
    assert views._event_type({"recent_fraction": 0.6}) == "breaking"
    assert views._event_type({"recent_fraction": 0.2}) == "developing"
    assert views._event_type({"recent_fraction": 0.0}) == "trending"


def test_cluster_signature_term_groups_singletons():
    articles = [
        {"terms": {"powell", "reserve"}, "title": "one"},
        {"terms": {"powell", "inflation"}, "title": "two"},
        {"terms": set(), "title": "empty"},
    ]
    labels = views._cluster_signature_term(articles)
    assert len(labels) == 3
    # Empty-terms article gets its own distinct label.
    assert labels[2] != labels[0] or labels[2] != labels[1]


# --------------------------------------------------------------------------- #
# _fetch_recent (real SQL against in-memory DuckDB)
# --------------------------------------------------------------------------- #

def test_fetch_recent_returns_shaped_articles(duck_conn):
    articles = run(views._fetch_recent(days=7))
    assert len(articles) == 6
    a = articles[0]
    assert set(a.keys()) >= {
        "id", "title", "content", "publish_date", "source",
        "category", "sentiment", "terms", "is_recent",
    }
    assert isinstance(a["terms"], set)
    assert isinstance(a["sentiment"], float)
    # At least one article is inside the 24h recent window.
    assert any(art["is_recent"] for art in articles)


def test_fetch_recent_category_filter(duck_conn):
    world = run(views._fetch_recent(days=7, category="World"))
    assert len(world) == 2
    assert {a["category"] for a in world} == {"World"}


def test_fetch_recent_respects_day_window(duck_conn):
    # 0-day window: cutoff == now, so nothing (all rows are in the past).
    articles = run(views._fetch_recent(days=0))
    assert articles == []


# --------------------------------------------------------------------------- #
# get_trending_topics
# --------------------------------------------------------------------------- #

def test_get_trending_topics_surfaces_multiword_entities(duck_conn):
    topics = run(views.get_trending_topics(days=7))
    assert isinstance(topics, list)
    assert len(topics) >= 1
    names = {t["topic"] for t in topics}
    # Corroborated multi-word entity should surface (Powell in 3 articles).
    assert any("Powell" in n for n in names)
    top = topics[0]
    assert set(top.keys()) == {
        "topic", "topic_name", "article_count", "avg_probability",
        "avg_sentiment", "growth_rate",
    }
    assert top["article_count"] >= 2
    assert 0.0 <= top["avg_probability"] <= 1.0
    # topics are sorted by article_count desc
    counts = [t["article_count"] for t in topics]
    assert counts == sorted(counts, reverse=True)


def test_get_trending_topics_empty(empty_conn):
    assert run(views.get_trending_topics(days=7)) == []


# --------------------------------------------------------------------------- #
# get_event_clusters
# --------------------------------------------------------------------------- #

def test_get_event_clusters_shape_and_ids(duck_conn):
    clusters = run(views.get_event_clusters(days_back=7, limit=20))
    assert isinstance(clusters, list)
    assert len(clusters) >= 1
    c = clusters[0]
    required = {
        "cluster_id", "cluster_name", "event_type", "category",
        "cluster_size", "trending_score", "impact_score", "velocity_score",
        "significance_score", "first_article_date", "last_article_date",
        "event_duration_hours", "primary_sources", "key_entities",
        "status", "created_at", "avg_sentiment", "sample_headlines",
    }
    assert required.issubset(c.keys())
    assert c["cluster_id"].startswith("cl-")
    assert c["status"] == "active"
    assert c["event_type"] in {"breaking", "developing", "trending"}
    # ISO-formatted dates round-trip.
    datetime.fromisoformat(c["first_article_date"])
    datetime.fromisoformat(c["created_at"])


def test_get_event_clusters_limit(duck_conn):
    clusters = run(views.get_event_clusters(days_back=7, limit=1))
    assert len(clusters) == 1


def test_get_event_clusters_category_filter(duck_conn):
    clusters = run(views.get_event_clusters(days_back=7, category="World"))
    # Only World-category articles feed the clustering.
    assert clusters  # non-empty
    assert all(c["category"] == "World" for c in clusters)


def test_get_event_clusters_event_type_filter(duck_conn):
    all_clusters = run(views.get_event_clusters(days_back=7))
    present_types = {c["event_type"] for c in all_clusters}
    a_type = next(iter(present_types))
    filtered = run(views.get_event_clusters(days_back=7, event_type=a_type))
    assert filtered  # at least the ones matching survive
    assert all(c["event_type"] == a_type for c in filtered)
    # A non-existent event type filters everything out.
    assert run(views.get_event_clusters(days_back=7, event_type="nonexistent")) == []


def test_get_event_clusters_empty(empty_conn):
    assert run(views.get_event_clusters(days_back=7)) == []


# --------------------------------------------------------------------------- #
# get_breaking_news
# --------------------------------------------------------------------------- #

def test_get_breaking_news_shape(duck_conn):
    events = run(views.get_breaking_news(hours_back=48, limit=10))
    assert isinstance(events, list)
    assert len(events) >= 1
    e = events[0]
    required = {
        "cluster_id", "cluster_name", "event_type", "category",
        "trending_score", "impact_score", "velocity_score", "cluster_size",
        "first_article_date", "last_article_date", "peak_activity_date",
        "event_duration_hours", "sample_headlines", "source_count",
        "avg_confidence",
    }
    assert required.issubset(e.keys())
    assert e["cluster_id"].startswith("bn-")
    assert isinstance(e["sample_headlines"], str)  # joined with " | "
    assert e["avg_confidence"] == 0.8


def test_get_breaking_news_limit(duck_conn):
    events = run(views.get_breaking_news(hours_back=48, limit=2))
    assert len(events) <= 2


def test_get_breaking_news_empty(empty_conn):
    assert run(views.get_breaking_news(hours_back=24)) == []


# --------------------------------------------------------------------------- #
# get_entity_graph
# --------------------------------------------------------------------------- #

def test_get_entity_graph_nodes_and_edges(duck_conn):
    graph = run(views.get_entity_graph(days=7, max_nodes=14))
    assert set(graph.keys()) == {"nodes", "edges", "node_count", "edge_count"}
    assert graph["node_count"] == len(graph["nodes"])
    assert graph["edge_count"] == len(graph["edges"])
    assert graph["nodes"], "expected at least one entity node"
    node = graph["nodes"][0]
    assert set(node.keys()) == {"id", "label", "type", "color", "count", "degree"}
    assert node["type"] in {"org", "person", "topic", "place"}
    # Node ids are lowercase canonical keys.
    assert node["id"] == node["id"].lower()
    for edge in graph["edges"]:
        assert set(edge.keys()) == {"source", "target", "weight"}
        assert edge["weight"] >= 1


def test_get_entity_graph_max_nodes_cap(duck_conn):
    graph = run(views.get_entity_graph(days=7, max_nodes=3))
    assert len(graph["nodes"]) <= 3


def test_get_entity_graph_empty(empty_conn):
    graph = run(views.get_entity_graph(days=7))
    assert graph == {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0}


# --------------------------------------------------------------------------- #
# get_sentiment_heatmap
# --------------------------------------------------------------------------- #

def test_get_sentiment_heatmap_shape(duck_conn):
    hm = run(views.get_sentiment_heatmap(days=14, max_topics=6))
    assert set(hm.keys()) == {"topics", "cols", "labels", "seed"}
    assert hm["cols"] == 14
    assert len(hm["labels"]) == 14
    assert hm["topics"], "expected top categories"
    # seed is topics x cols matrix of rounded floats.
    assert len(hm["seed"]) == len(hm["topics"])
    for row in hm["seed"]:
        assert len(row) == 14
        assert all(isinstance(v, float) for v in row)


def test_get_sentiment_heatmap_max_topics(duck_conn):
    hm = run(views.get_sentiment_heatmap(days=14, max_topics=1))
    assert len(hm["topics"]) == 1
    assert len(hm["seed"]) == 1


def test_get_sentiment_heatmap_empty(empty_conn):
    hm = run(views.get_sentiment_heatmap(days=14))
    assert hm == {"topics": [], "cols": 0, "labels": [], "seed": []}


# --------------------------------------------------------------------------- #
# get_topic_sentiment
# --------------------------------------------------------------------------- #

def test_get_topic_sentiment_shape(duck_conn):
    # min_articles=2 so our small corpus yields topics.
    topics = run(views.get_topic_sentiment(days=7, min_articles=2, max_topics=12))
    assert isinstance(topics, list)
    assert topics, "expected keyword topics"
    t = topics[0]
    assert set(t.keys()) == {"topic", "total_articles", "sentiments"}
    assert t["total_articles"] >= 2
    # sentiments bucketed by label with count/avg_score.
    for label, stats in t["sentiments"].items():
        assert label in {"positive", "negative", "neutral"}
        assert set(stats.keys()) == {"count", "avg_score"}
        assert stats["count"] >= 1
    # sorted by total_articles desc.
    totals = [x["total_articles"] for x in topics]
    assert totals == sorted(totals, reverse=True)


def test_get_topic_sentiment_min_articles_filter(duck_conn):
    # Very high threshold filters everything out.
    assert run(views.get_topic_sentiment(days=7, min_articles=100)) == []


def test_get_topic_sentiment_max_topics_cap(duck_conn):
    topics = run(views.get_topic_sentiment(days=7, min_articles=2, max_topics=1))
    assert len(topics) <= 1


def test_get_topic_sentiment_empty(empty_conn):
    assert run(views.get_topic_sentiment(days=7)) == []


# --------------------------------------------------------------------------- #
# Aggregation / alias resolution internals
# --------------------------------------------------------------------------- #

def test_aggregate_entities_resolves_surname_alias(duck_conn):
    articles = run(views._fetch_recent(days=7))
    doc_count, label_form, per_article, entity_docs = views._aggregate_entities(articles)
    # "powell" surname mentions should fold into "jerome powell".
    assert "jerome powell" in doc_count
    # After alias resolution the bare surname key is gone / merged.
    assert doc_count["jerome powell"] >= 2
    assert "jerome powell" in entity_docs
    assert len(per_article) == len(articles)


def test_build_clusters_uses_sklearn_when_available(duck_conn):
    pytest.importorskip("sklearn")
    articles = run(views._fetch_recent(days=7))
    # sklearn path returns labels (not None) for a non-trivial corpus.
    labels = views._cluster_sklearn(articles, threshold=0.18)
    assert labels is not None
    assert len(labels) == len(articles)
    clusters = views._build_clusters(articles)
    assert clusters
    # The Powell/Fed articles should co-cluster (largest cluster size >= 2).
    assert max(c["size"] for c in clusters) >= 2


def test_cluster_sklearn_missing_returns_none(duck_conn, monkeypatch):
    # Force the sklearn import to fail inside _cluster_sklearn.
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("sklearn"):
            raise ImportError("sklearn disabled for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    articles = run(views._fetch_recent(days=7))
    assert views._cluster_sklearn(articles, threshold=0.18) is None
    # _build_clusters must fall back to the signature-term clusterer.
    clusters = views._build_clusters(articles)
    assert clusters
