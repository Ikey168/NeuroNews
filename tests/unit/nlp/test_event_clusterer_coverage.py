"""Coverage-focused tests for src/nlp/event_clusterer.py.

Exercises the async clustering pipeline end-to-end with real sklearn/numpy on
small synthetic embeddings, plus the DB persistence paths (mocked psycopg2),
category inference, event significance ranking, and error handling.
"""

import os
import sys
from collections import Counter
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

np = pytest.importorskip("numpy")
pytest.importorskip("sklearn")

import nlp.event_clusterer as mod  # noqa: E402
from nlp.event_clusterer import EventClusterer  # noqa: E402


def _make_embeddings(n_per_cluster=4, dim=8):
    """Build two well-separated clusters of article embedding records."""
    rng = np.random.RandomState(0)
    base_time = datetime(2026, 6, 1, 12, 0, 0)
    data = []
    centers = [np.zeros(dim), np.ones(dim) * 5.0]
    idx = 0
    for c, center in enumerate(centers):
        for j in range(n_per_cluster):
            vec = center + rng.normal(0, 0.15, dim)
            data.append(
                {
                    "article_id": "a{0}".format(idx),
                    "embedding_vector": vec.tolist(),
                    "embedding_model": "all-MiniLM-L6-v2",
                    "title": "Apple United States news number {0}".format(idx)
                    if c == 0
                    else "China market economy report {0}".format(idx),
                    "content": "Tim Cook and Google talked about AI technology software."
                    if c == 0
                    else "The stock market and economy showed business revenue growth.",
                    "source": "src{0}".format(j % 3),
                    "published_date": base_time + timedelta(hours=idx),
                    "source_credibility": "trusted",
                    "sentiment_score": 0.9 if c == 0 else 0.1,
                    "category": "Technology" if c == 0 else "Business",
                }
            )
            idx += 1
    return data


def _article(**over):
    base = dict(
        article_id="x",
        title="Apple announces product in United States",
        content="Tim Cook spoke. Google and OpenAI responded about AI.",
        source="bbc",
        published_date=datetime(2026, 6, 1, 12, 0, 0),
        source_credibility="trusted",
        sentiment_score=0.9,
        category="Technology",
        embedding_vector=[0.1, 0.2, 0.3, 0.4],
        embedding_model="m",
    )
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# detect_events end-to-end
# ---------------------------------------------------------------------------
class TestDetectEvents:
    @pytest.mark.asyncio
    async def test_too_few_articles(self):
        clusterer = EventClusterer(min_cluster_size=3)
        out = await clusterer.detect_events([_article(), _article()])
        assert out == []

    @pytest.mark.asyncio
    async def test_full_pipeline_no_db(self):
        clusterer = EventClusterer(conn_params=None, min_cluster_size=3, max_clusters=5)
        data = _make_embeddings(n_per_cluster=4)
        events = await clusterer.detect_events(data, category="Technology")
        assert isinstance(events, list)
        assert len(events) >= 1
        ev = events[0]
        # event structure produced by _create_event_from_cluster
        assert ev["cluster_size"] >= 3
        assert "significance_score" in ev
        assert ev["category"] == "Technology"
        assert 0.0 <= ev["trending_score"] <= 10.0
        # statistics updated
        stats = clusterer.get_statistics()
        assert stats["articles_clustered"] == len(data)
        assert stats["events_detected"] == len(events)
        assert stats["last_clustering_run"] is not None

    @pytest.mark.asyncio
    async def test_pipeline_stores_when_conn_params(self, monkeypatch):
        clusterer = EventClusterer(
            conn_params={"host": "x"}, min_cluster_size=3, max_clusters=5
        )
        # Capture the store call rather than hitting a DB.
        stored = {}

        async def fake_store(events):
            stored["events"] = events
            return len(events)

        monkeypatch.setattr(clusterer, "_store_events", fake_store)
        data = _make_embeddings(n_per_cluster=4)
        events = await clusterer.detect_events(data)
        assert "events" in stored
        assert len(stored["events"]) == len(events)

    @pytest.mark.asyncio
    async def test_detect_events_reraises_on_error(self, monkeypatch):
        clusterer = EventClusterer(conn_params=None, min_cluster_size=3)

        def boom(*a, **k):
            raise ValueError("scaler boom")

        monkeypatch.setattr(mod, "StandardScaler", lambda: MagicMock(
            fit_transform=MagicMock(side_effect=boom)))
        with pytest.raises(ValueError):
            await clusterer.detect_events(_make_embeddings(n_per_cluster=4))


# ---------------------------------------------------------------------------
# clustering internals
# ---------------------------------------------------------------------------
class TestClusteringInternals:
    def test_find_optimal_clusters_small_returns_two(self):
        clusterer = EventClusterer(min_cluster_size=3, max_clusters=20)
        emb = np.random.RandomState(1).rand(4, 5)  # 4 samples // 3 -> max_k 1 -> <2
        assert clusterer._find_optimal_clusters(emb) == 2

    def test_find_optimal_clusters_returns_int(self):
        clusterer = EventClusterer(min_cluster_size=3, max_clusters=5)
        data = _make_embeddings(n_per_cluster=5)
        emb = np.array([d["embedding_vector"] for d in data])
        from sklearn.preprocessing import StandardScaler
        emb = StandardScaler().fit_transform(emb)
        k = clusterer._find_optimal_clusters(emb)
        assert isinstance(k, int)
        assert k >= 2

    def test_perform_clustering_kmeans_metrics(self):
        clusterer = EventClusterer(clustering_method="kmeans")
        data = _make_embeddings(n_per_cluster=4)
        emb = np.array([d["embedding_vector"] for d in data])
        labels, metrics = clusterer._perform_clustering(emb, n_clusters=2)
        assert len(labels) == len(data)
        assert "silhouette_score" in metrics
        assert "inertia" in metrics
        assert metrics["n_clusters"] == 2

    def test_perform_clustering_dbscan(self):
        clusterer = EventClusterer(clustering_method="dbscan", min_cluster_size=3)
        data = _make_embeddings(n_per_cluster=5)
        emb = np.array([d["embedding_vector"] for d in data])
        # dbscan works on raw (well separated) points
        labels, metrics = clusterer._perform_clustering(emb, n_clusters=2)
        assert "noise_points" in metrics
        assert "n_clusters" in metrics

    def test_perform_clustering_unknown_method_raises(self):
        clusterer = EventClusterer(clustering_method="unknown_method")
        emb = np.random.RandomState(2).rand(6, 4)
        with pytest.raises(ValueError):
            clusterer._perform_clustering(emb, n_clusters=2)


# ---------------------------------------------------------------------------
# cluster -> event conversion
# ---------------------------------------------------------------------------
class TestClusterToEvent:
    @pytest.mark.asyncio
    async def test_process_clusters_skips_small_and_noise(self):
        clusterer = EventClusterer(min_cluster_size=3)
        data = _make_embeddings(n_per_cluster=3)
        # 6 items -> labels: cluster 0 (3 items), cluster 1 (2 items), one noise -1
        labels = np.array([0, 0, 0, 1, 1, -1])
        events = await clusterer._process_clusters_to_events(
            data, labels, {"silhouette_score": 0.5}, None
        )
        # only the 3-member cluster becomes an event
        assert len(events) == 1
        assert events[0]["cluster_size"] == 3

    @pytest.mark.asyncio
    async def test_create_event_too_small_returns_none(self):
        clusterer = EventClusterer(min_cluster_size=3)
        out = await clusterer._create_event_from_cluster(
            0, [_article(), _article()], {}, None
        )
        assert out is None

    @pytest.mark.asyncio
    async def test_create_event_full_structure(self):
        clusterer = EventClusterer(min_cluster_size=3)
        base = datetime(2026, 6, 1, 12, 0, 0)
        arts = [
            _article(article_id="a{0}".format(i),
                     published_date=base + timedelta(hours=i))
            for i in range(3)
        ]
        ev = await clusterer._create_event_from_cluster(
            2, arts, {"silhouette_score": 0.42}, "Technology"
        )
        assert ev is not None
        assert ev["cluster_size"] == 3
        assert ev["silhouette_score"] == 0.42
        assert ev["event_type"] in {"breaking", "trending", "developing", "ongoing"}
        assert len(ev["articles"]) == 3
        # first article by date is the representative
        assert ev["articles"][0]["is_cluster_representative"] is True
        assert "cohesion_score" in ev


# ---------------------------------------------------------------------------
# category inference + significance
# ---------------------------------------------------------------------------
class TestInferenceAndSignificance:
    def test_infer_category_from_existing(self):
        clusterer = EventClusterer()
        arts = [_article(category="Health"), _article(category="Health"),
                _article(category="Sports")]
        assert clusterer._infer_category(arts) == "Health"

    def test_infer_category_from_keywords(self):
        clusterer = EventClusterer()
        arts = [
            _article(category=None,
                     title="Government election vote", content="senate policy law"),
            _article(category=None,
                     title="President congress", content="election vote government"),
        ]
        assert clusterer._infer_category(arts) == "Politics"

    def test_infer_category_no_keyword_match_returns_first(self):
        # With no category keys and zero keyword matches, the scored branch
        # returns the first (arbitrary max) category rather than "General".
        clusterer = EventClusterer()
        arts = [_article(category=None, title="zzz", content="qqq")]
        result = clusterer._infer_category(arts)
        assert result in {
            "Technology", "Politics", "Health", "Business", "Sports",
            "Entertainment", "General",
        }

    def test_infer_category_exception_returns_general(self):
        # An article dict missing the required 'title' key makes the internal
        # f-string raise KeyError, which is caught and returns "General".
        clusterer = EventClusterer()
        assert clusterer._infer_category([{"content": "x"}]) == "General"

    def test_calculate_event_significance_error_returns_input(self):
        clusterer = EventClusterer()
        # Missing keys -> KeyError inside the loop -> except branch returns list
        bad = [{"trending_score": 1}]
        out = clusterer._calculate_event_significance(bad)
        assert out is bad

    def test_calculate_event_significance_sorts(self):
        clusterer = EventClusterer()
        events = [
            {"trending_score": 1, "impact_score": 10, "velocity_score": 1,
             "cluster_size": 3},
            {"trending_score": 9, "impact_score": 90, "velocity_score": 9,
             "cluster_size": 15},
        ]
        out = clusterer._calculate_event_significance(events)
        assert out[0]["significance_score"] >= out[1]["significance_score"]
        assert all("significance_score" in e for e in out)


# ---------------------------------------------------------------------------
# helper exception fallbacks
# ---------------------------------------------------------------------------
class TestHelperFallbacks:
    def test_generate_cluster_name_error_fallback(self):
        clusterer = EventClusterer()
        # missing 'title' -> exception -> "Event <date>" fallback
        name = clusterer._generate_cluster_name([{"content": "x"}])
        assert name.startswith("Event ")

    def test_determine_event_type_boundaries(self):
        clusterer = EventClusterer()
        assert clusterer._determine_event_type([], 1) == "breaking"
        assert clusterer._determine_event_type([], 6) == "trending"
        assert clusterer._determine_event_type([], 48) == "developing"
        assert clusterer._determine_event_type([], 200) == "ongoing"

    def test_extract_geographic_focus_error_returns_empty(self):
        clusterer = EventClusterer()
        # article missing 'title' triggers KeyError -> [] fallback
        assert clusterer._extract_geographic_focus([{"content": "x"}]) == []

    def test_extract_key_entities_error_returns_empty(self):
        clusterer = EventClusterer()
        assert clusterer._extract_key_entities([{"content": "x"}]) == []

    def test_trending_score_error_returns_default(self):
        clusterer = EventClusterer()
        # empty list -> max() on empty -> exception -> 1.0
        assert clusterer._calculate_trending_score([], 1.0) == 1.0

    def test_impact_score_error_returns_default(self):
        clusterer = EventClusterer()
        # empty articles -> division by zero in credibility_factor -> 50.0
        assert clusterer._calculate_impact_score([], Counter()) == 50.0

    def test_velocity_score_zero_duration(self):
        clusterer = EventClusterer()
        assert clusterer._calculate_velocity_score([_article()], 0) == 10.0

    def test_velocity_score_positive(self):
        clusterer = EventClusterer()
        v = clusterer._calculate_velocity_score([_article()] * 10, 5.0)
        assert 0 < v <= 10.0

    def test_find_peak_activity_error_fallback(self):
        clusterer = EventClusterer()
        # empty list -> exception path -> datetime.now()
        peak = clusterer._find_peak_activity([])
        assert isinstance(peak, datetime)


# ---------------------------------------------------------------------------
# DB persistence (mocked psycopg2)
# ---------------------------------------------------------------------------
def _mock_conn(monkeypatch, rows=None):
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=None)
    cur.fetchall.return_value = rows or []
    conn = MagicMock()
    conn.cursor.return_value = cur
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=None)
    monkeypatch.setattr(mod.psycopg2, "connect", MagicMock(return_value=conn))
    return conn, cur


class TestPersistence:
    @pytest.mark.asyncio
    async def test_store_events_inserts(self, monkeypatch):
        clusterer = EventClusterer(conn_params={"host": "x"})
        conn, cur = _mock_conn(monkeypatch)
        base = datetime(2026, 6, 1, 12, 0, 0)
        arts = [
            _article(article_id="a{0}".format(i),
                     published_date=base + timedelta(hours=i))
            for i in range(3)
        ]
        ev = await clusterer._create_event_from_cluster(
            0, arts, {"silhouette_score": 0.3}, "Technology"
        )
        count = await clusterer._store_events([ev])
        assert count == 1
        assert cur.execute.called
        assert conn.commit.called

    @pytest.mark.asyncio
    async def test_store_events_empty(self):
        clusterer = EventClusterer(conn_params={"host": "x"})
        assert await clusterer._store_events([]) == 0

    @pytest.mark.asyncio
    async def test_store_events_db_error_returns_zero(self, monkeypatch):
        clusterer = EventClusterer(conn_params={"host": "x"})
        monkeypatch.setattr(
            mod.psycopg2, "connect",
            MagicMock(side_effect=RuntimeError("db down")))
        assert await clusterer._store_events([{"cluster_id": "c"}]) == 0

    @pytest.mark.asyncio
    async def test_get_breaking_news_no_conn(self):
        clusterer = EventClusterer(conn_params=None)
        assert await clusterer.get_breaking_news() == []

    @pytest.mark.asyncio
    async def test_get_breaking_news_returns_rows(self, monkeypatch):
        clusterer = EventClusterer(conn_params={"host": "x"})
        row = {
            "cluster_id": "c1",
            "category": "Technology",
            "first_article_date": datetime(2026, 6, 1, 10, 0, 0),
            "last_article_date": datetime(2026, 6, 1, 12, 0, 0),
            "peak_activity_date": None,
            "trending_score": 5.0,
        }
        _mock_conn(monkeypatch, rows=[row])
        out = await clusterer.get_breaking_news(category="Technology", limit=5)
        assert len(out) == 1
        # dates converted to ISO strings
        assert isinstance(out[0]["first_article_date"], str)
        assert out[0]["peak_activity_date"] is None

    @pytest.mark.asyncio
    async def test_get_breaking_news_db_error(self, monkeypatch):
        clusterer = EventClusterer(conn_params={"host": "x"})
        monkeypatch.setattr(
            mod.psycopg2, "connect",
            MagicMock(side_effect=RuntimeError("boom")))
        assert await clusterer.get_breaking_news() == []
