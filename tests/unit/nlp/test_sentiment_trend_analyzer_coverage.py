"""Coverage tests for src/nlp/sentiment_trend_analyzer.py.

Fills the remaining gaps left by test_sentiment_trend_analyzer_extra.py and
test_sentiment_trend_analyzer_core.py:

* error re-raise in ``analyze_historical_trends`` / ``generate_sentiment_alerts``
* the "skip topics below min_articles" branch inside ``generate_sentiment_alerts``
* default time-granularity aggregation and the empty-bucket skip
* the decreasing-trend direction branch of ``_calculate_trend_summary``
* the exception handler in ``_detect_sentiment_alerts``
* ``_store_alerts`` re-raise, ``get_topic_trend_summary`` error path, and the
  per-topic + outer error paths of ``update_topic_summaries``.

psycopg2 / analyzer / topic-extractor are mocked; no DB is contacted.
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("scipy")

# Warm up torch before coverage's C tracer (nlp package import pulls torch in).
try:  # pragma: no cover - defensive
    import torch  # noqa: F401
except Exception:  # pragma: no cover
    pass

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import nlp.sentiment_trend_analyzer as mod  # noqa: E402
from nlp.sentiment_trend_analyzer import (  # noqa: E402
    SentimentTrendAnalyzer,
    TopicTrendSummary,
)


@pytest.fixture
def analyzer():
    with patch.object(mod, "psycopg2", MagicMock()):
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
        "id": _id,
        "topic": topic,
        "publish_date": date or datetime(2026, 1, 15).date(),
        "sentiment_score": score,
        "sentiment_confidence": conf,
    }


class TestOrchestrationErrors:
    @pytest.mark.asyncio
    async def test_analyze_historical_trends_reraises(self, analyzer):
        async def _boom(topic, start, end):
            raise RuntimeError("fetch exploded")

        with patch.object(analyzer, "_fetch_sentiment_data", side_effect=_boom):
            with pytest.raises(RuntimeError, match="fetch exploded"):
                await analyzer.analyze_historical_trends(topic="tech")

    @pytest.mark.asyncio
    async def test_generate_sentiment_alerts_reraises(self, analyzer):
        async def _boom(topic, start, end):
            raise RuntimeError("gen exploded")

        with patch.object(analyzer, "_fetch_sentiment_data", side_effect=_boom):
            with pytest.raises(RuntimeError, match="gen exploded"):
                await analyzer.generate_sentiment_alerts(topic="tech")

    @pytest.mark.asyncio
    async def test_generate_alerts_skips_topics_below_min(self, analyzer):
        # 2 points for a topic; min_articles_for_trend is 5 -> topic skipped,
        # so no alerts are produced and _store_alerts is never called.
        data = [datapoint(topic="tech", _id=f"a{i}") for i in range(2)]

        async def _fetch(topic, start, end):
            return data

        store = MagicMock()
        with patch.object(analyzer, "_fetch_sentiment_data", side_effect=_fetch), patch.object(
            analyzer, "_store_alerts", store
        ):
            out = await analyzer.generate_sentiment_alerts(topic="tech")
        assert out == []
        store.assert_not_called()


class TestAggregationAndTrend:
    def test_aggregate_default_granularity(self, analyzer):
        # An unknown granularity falls through to the daily default (line ~467).
        data = [
            datapoint(date=datetime(2026, 1, 10).date(), _id="a1"),
            datapoint(date=datetime(2026, 1, 10).date(), _id="a2"),
            datapoint(date=datetime(2026, 1, 11).date(), _id="a3"),
        ]
        agg = analyzer._aggregate_by_time_granularity(data, "unknown-granularity")
        assert "2026-01-10" in agg
        assert len(agg["2026-01-10"]) == 2
        assert "2026-01-11" in agg

    def test_aggregate_weekly_and_monthly(self, analyzer):
        data = [datapoint(date=datetime(2026, 3, 18).date(), _id="a1")]
        weekly = analyzer._aggregate_by_time_granularity(data, "weekly")
        # Monday of that week (2026-03-16)
        assert "2026-03-16" in weekly
        monthly = analyzer._aggregate_by_time_granularity(data, "monthly")
        assert "2026-03" in monthly

    def test_create_trend_points_skips_empty_bucket(self, analyzer):
        aggregated = {
            "2026-01-10": [],  # empty bucket -> continue (line ~481)
            "2026-01-11": [datapoint(date=datetime(2026, 1, 11).date(), score=0.4)],
        }
        points = analyzer._create_trend_points("tech", aggregated)
        assert len(points) == 1
        assert points[0].metadata["date_key"] == "2026-01-11"

    def test_calculate_trend_summary_decreasing(self, analyzer):
        # strictly decreasing scores -> slope < -0.01 -> "decreasing" (line 579)
        aggregated = {
            f"2026-01-{10 + i:02d}": [
                datapoint(date=datetime(2026, 1, 10 + i).date(), score=0.9 - 0.2 * i)
            ]
            for i in range(5)
        }
        points = analyzer._create_trend_points("tech", aggregated)
        summary = analyzer._calculate_trend_summary(
            "tech", points, (datetime(2026, 1, 1), datetime(2026, 1, 31))
        )
        assert summary.trend_direction == "decreasing"
        assert summary.trend_strength > 0

    def test_calculate_trend_summary_empty_points(self, analyzer):
        summary = analyzer._calculate_trend_summary(
            "tech", [], (datetime(2026, 1, 1), datetime(2026, 1, 31))
        )
        assert summary.trend_direction == "stable"
        assert summary.data_points == []


class TestDetectAlertExceptions:
    @pytest.mark.asyncio
    async def test_detect_alerts_swallows_exception(self, analyzer):
        # Malformed items (missing 'publish_date') make the sort raise; the
        # method logs and returns whatever alerts it accumulated (empty).
        bad_data = [{"id": "x", "sentiment_score": 0.5}, {"id": "y"}]
        out = await analyzer._detect_sentiment_alerts("tech", bad_data, 7)
        assert out == []


class TestStoreAndSummaries:
    @pytest.mark.asyncio
    async def test_store_alerts_reraises_on_error(self, analyzer):
        alert = analyzer._create_alert(
            topic="tech",
            alert_type="significant_shift",
            current_sentiment=0.6,
            previous_sentiment=0.1,
            change_magnitude=0.5,
            change_percentage=500.0,
            time_window="7d",
            affected_articles=["a1"],
        )
        fake_pg = MagicMock()
        fake_pg.connect.side_effect = Exception("store fail")
        with patch.object(mod, "psycopg2", fake_pg):
            with pytest.raises(Exception, match="store fail"):
                await analyzer._store_alerts([alert])

    @pytest.mark.asyncio
    async def test_get_topic_trend_summary_error_returns_none(self, analyzer):
        async def _boom(topic, start_date, end_date):
            raise RuntimeError("analyze fail")

        with patch.object(analyzer, "analyze_historical_trends", side_effect=_boom):
            res = await analyzer.get_topic_trend_summary("tech", days=10)
        assert res is None

    @pytest.mark.asyncio
    async def test_update_topic_summaries_per_topic_error_continues(self, analyzer):
        cursor = MagicMock()
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)
        cursor.fetchall.return_value = [("tech",), ("politics",)]
        conn = MagicMock()
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cursor
        fake_pg = MagicMock()
        fake_pg.connect.return_value = conn

        summary = TopicTrendSummary(
            topic="tech",
            time_range=(datetime(2026, 1, 1), datetime(2026, 1, 31)),
            current_sentiment=0.5,
            average_sentiment=0.4,
            sentiment_volatility=0.1,
            trend_direction="stable",
            trend_strength=0.0,
            significant_changes=[],
            data_points=[],
            statistical_summary={},
        )

        async def _gts(topic):
            if topic == "tech":
                raise RuntimeError("per-topic boom")  # hits inner except
            return summary

        async def _sts(summary):
            return None

        with patch.object(mod, "psycopg2", fake_pg), patch.object(
            analyzer, "get_topic_trend_summary", side_effect=_gts
        ), patch.object(analyzer, "_store_topic_summary", side_effect=_sts) as sts:
            # must not raise despite the per-topic error
            await analyzer.update_topic_summaries()
        # only the successful topic ("politics") reached _store_topic_summary
        assert sts.call_count == 1

    @pytest.mark.asyncio
    async def test_update_topic_summaries_outer_error_swallowed(self, analyzer):
        fake_pg = MagicMock()
        fake_pg.connect.side_effect = Exception("db down")
        with patch.object(mod, "psycopg2", fake_pg):
            # outer try/except logs and returns without raising
            await analyzer.update_topic_summaries()

    @pytest.mark.asyncio
    async def test_update_topic_summaries_skips_none_summary(self, analyzer):
        cursor = MagicMock()
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)
        cursor.fetchall.return_value = [("tech",)]
        conn = MagicMock()
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cursor
        fake_pg = MagicMock()
        fake_pg.connect.return_value = conn

        async def _gts(topic):
            return None  # summary is None -> _store_topic_summary skipped

        with patch.object(mod, "psycopg2", fake_pg), patch.object(
            analyzer, "get_topic_trend_summary", side_effect=_gts
        ), patch.object(analyzer, "_store_topic_summary") as sts:
            await analyzer.update_topic_summaries()
        sts.assert_not_called()
