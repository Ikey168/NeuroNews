"""Tests for pure helper logic in src/nlp/event_clusterer.py."""

import os
import sys
from collections import Counter
from datetime import datetime, timedelta

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("numpy")

from nlp.event_clusterer import EventClusterer  # noqa: E402


@pytest.fixture
def clusterer():
    return EventClusterer()


def article(**over):
    base = dict(
        title="Apple announces new product in United States",
        content="Tim Cook spoke about it. Google responded.",
        source="bbc",
        published_date=datetime.now(),
        source_credibility="trusted",
        sentiment_score=0.9,
        category="Technology",
    )
    base.update(over)
    return base


class TestInit:
    def test_defaults(self, clusterer):
        assert clusterer.min_cluster_size == 3
        assert clusterer.clustering_method == "kmeans"
        assert clusterer.stats["events_detected"] == 0

    def test_get_statistics(self, clusterer):
        stats = clusterer.get_statistics()
        assert "articles_clustered" in stats


class TestClusterName:
    def test_common_words(self, clusterer):
        arts = [article(title="Apple News Today"), article(title="Apple News Update")]
        name = clusterer._generate_cluster_name(arts)
        assert "Apple" in name or "News" in name

    def test_fallback_to_first_title(self, clusterer):
        arts = [article(title="Unique singular headline here")]
        name = clusterer._generate_cluster_name(arts)
        assert name.startswith("Unique")


class TestEventType:
    @pytest.mark.parametrize("hours,expected", [
        (1, "breaking"), (6, "trending"), (48, "developing"), (100, "ongoing"),
    ])
    def test_determine_event_type(self, clusterer, hours, expected):
        assert clusterer._determine_event_type([article()], hours) == expected


class TestExtraction:
    def test_geographic_focus(self, clusterer):
        locs = clusterer._extract_geographic_focus(
            [article(title="News from China and United States")]
        )
        assert any("China" in str(loc) for loc in locs)

    def test_key_entities(self, clusterer):
        ents = clusterer._extract_key_entities(
            [article(title="Apple and Google and OpenAI announce")]
        )
        assert len(ents) >= 1


class TestScores:
    def test_trending_score_range(self, clusterer):
        arts = [article(source=f"s{i}", published_date=datetime.now()) for i in range(5)]
        score = clusterer._calculate_trending_score(arts, duration_hours=2.0)
        assert 0.0 <= score <= 10.0

    def test_impact_score_range(self, clusterer):
        arts = [article() for _ in range(3)]
        score = clusterer._calculate_impact_score(arts, Counter({"bbc": 3}))
        assert 0.0 <= score <= 100.0

    def test_velocity_score(self, clusterer):
        arts = [article() for _ in range(10)]
        assert clusterer._calculate_velocity_score(arts, 5.0) > 0
        assert clusterer._calculate_velocity_score(arts, 0) == 10.0

    def test_find_peak_activity(self, clusterer):
        now = datetime.now().replace(minute=0, second=0, microsecond=0)
        arts = [
            article(published_date=now),
            article(published_date=now),
            article(published_date=now - timedelta(hours=5)),
        ]
        peak = clusterer._find_peak_activity(arts)
        assert peak == now
