"""Tests for analytical methods of src/nlp/sentiment_trend_analyzer.py."""

import os
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import nlp.sentiment_trend_analyzer as sta  # noqa: E402
from nlp.sentiment_trend_analyzer import (  # noqa: E402
    SentimentTrendAnalyzer,
    SentimentTrendPoint,
    TrendAlert,
)


@pytest.fixture
def analyzer():
    with patch.object(sta, "psycopg2", MagicMock()):
        a = SentimentTrendAnalyzer(
            snowflake_account="acct",
            snowflake_user="u",
            snowflake_password="p",
            sentiment_analyzer=MagicMock(),
            topic_extractor=MagicMock(),
        )
    return a


def datapoint(topic="tech", date=None, score=0.5, conf=0.9, _id="a1"):
    return {
        "topic": topic,
        "publish_date": date or datetime(2026, 1, 15),
        "sentiment_score": score,
        "sentiment_confidence": conf,
        "id": _id,
    }


class TestDataclasses:
    def test_trend_point(self):
        p = SentimentTrendPoint(
            date=datetime(2026, 1, 1), topic="t", sentiment_score=0.5,
            sentiment_label="positive", confidence=0.9, article_count=3,
            source_articles=["a", "b"], metadata={},
        )
        assert p.article_count == 3

    def test_trend_alert(self):
        a = TrendAlert(
            alert_id="x", topic="t", alert_type="significant_shift", severity="high",
            current_sentiment=0.5, previous_sentiment=-0.2, change_magnitude=0.7,
            change_percentage=350.0, confidence=0.8, time_window="7d",
            triggered_at=datetime(2026, 1, 1), description="d",
            affected_articles=[], metadata={},
        )
        assert a.severity == "high"


class TestGroupByTopic:
    def test_groups(self, analyzer):
        data = [datapoint(topic="tech"), datapoint(topic="sports"), datapoint(topic="tech")]
        grouped = analyzer._group_data_by_topic(data)
        assert len(grouped["tech"]) == 2
        assert len(grouped["sports"]) == 1

    def test_unknown_topic(self, analyzer):
        grouped = analyzer._group_data_by_topic([{"publish_date": datetime(2026, 1, 1)}])
        assert "unknown" in grouped


class TestAggregateByGranularity:
    def test_daily(self, analyzer):
        data = [
            datapoint(date=datetime(2026, 1, 15)),
            datapoint(date=datetime(2026, 1, 15)),
            datapoint(date=datetime(2026, 1, 16)),
        ]
        agg = analyzer._aggregate_by_time_granularity(data, "daily")
        assert len(agg["2026-01-15"]) == 2
        assert len(agg["2026-01-16"]) == 1

    def test_monthly(self, analyzer):
        data = [
            datapoint(date=datetime(2026, 1, 5)),
            datapoint(date=datetime(2026, 1, 25)),
            datapoint(date=datetime(2026, 2, 1)),
        ]
        agg = analyzer._aggregate_by_time_granularity(data, "monthly")
        assert len(agg["2026-01"]) == 2
        assert len(agg["2026-02"]) == 1

    def test_weekly(self, analyzer):
        data = [datapoint(date=datetime(2026, 1, 14))]  # a Wednesday
        agg = analyzer._aggregate_by_time_granularity(data, "weekly")
        # week start is Monday 2026-01-12
        assert "2026-01-12" in agg


class TestCreateTrendPoints:
    def test_positive_label(self, analyzer):
        agg = {"2026-01-15": [datapoint(score=0.5), datapoint(score=0.7)]}
        points = analyzer._create_trend_points("tech", agg)
        assert len(points) == 1
        assert points[0].sentiment_label == "positive"
        assert points[0].article_count == 2

    def test_negative_label(self, analyzer):
        agg = {"2026-01-15": [datapoint(score=-0.5)]}
        points = analyzer._create_trend_points("tech", agg)
        assert points[0].sentiment_label == "negative"

    def test_neutral_label(self, analyzer):
        agg = {"2026-01-15": [datapoint(score=0.0)]}
        points = analyzer._create_trend_points("tech", agg)
        assert points[0].sentiment_label == "neutral"

    def test_monthly_date_parsing(self, analyzer):
        agg = {"2026-03": [datapoint(score=0.2)]}
        points = analyzer._create_trend_points("tech", agg)
        assert points[0].date == datetime(2026, 3, 1)

    def test_skips_empty_and_bad_date(self, analyzer):
        agg = {"": [datapoint(score=0.2)], "bad-key-xyz": [datapoint(score=0.2)]}
        points = analyzer._create_trend_points("tech", agg)
        assert points == []
