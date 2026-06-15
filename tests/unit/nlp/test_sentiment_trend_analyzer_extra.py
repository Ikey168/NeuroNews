"""Extra tests targeting coverage gaps in src/nlp/sentiment_trend_analyzer.py.

These complement test_sentiment_trend_analyzer_core.py and
test_sentiment_trend_analysis.py by exercising the DB-touching SQL methods
(schema init, fetch, store, summaries, active-alert parsing) and the async
orchestration paths, with real assertions on returned shapes/values.
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("scipy")

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import nlp.sentiment_trend_analyzer as mod  # noqa: E402
from nlp.sentiment_trend_analyzer import (  # noqa: E402
    SentimentTrendAnalyzer,
    SentimentTrendPoint,
    TopicTrendSummary,
    TrendAlert,
)


def _make_cursor(fetchall=None, fetchone=None, description=None):
    """Create a MagicMock cursor usable as a context manager."""
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=None)
    cur.fetchall = MagicMock(return_value=fetchall if fetchall is not None else [])
    cur.fetchone = MagicMock(return_value=fetchone)
    cur.description = description
    return cur


def _make_psycopg2(cursor):
    """Build a MagicMock psycopg2 whose connect() yields a conn with `cursor`."""
    fake = MagicMock()
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=None)
    conn.cursor = MagicMock(return_value=cursor)
    fake.connect = MagicMock(return_value=conn)
    return fake, conn


@pytest.fixture
def analyzer():
    """Analyzer constructed with psycopg2 patched (so __init__ schema init runs)."""
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


# --------------------------------------------------------------------------
# _initialize_database_schema
# --------------------------------------------------------------------------
class TestInitializeSchema:
    def test_init_runs_create_table_statements(self):
        cursor = _make_cursor()
        fake_psycopg2, conn = _make_psycopg2(cursor)
        with patch.object(mod, "psycopg2", fake_psycopg2):
            SentimentTrendAnalyzer(
                snowflake_account="acct",
                snowflake_user="u",
                snowflake_password="p",
                sentiment_analyzer=MagicMock(),
                topic_extractor=MagicMock(),
            )
        # connect called, and DDL executed (3 tables + 2 indexes = 5 execute calls)
        assert fake_psycopg2.connect.called
        assert cursor.execute.call_count >= 5
        executed_sql = " ".join(c.args[0] for c in cursor.execute.call_args_list)
        assert "CREATE TABLE IF NOT EXISTS sentiment_trends" in executed_sql
        assert "CREATE TABLE IF NOT EXISTS sentiment_alerts" in executed_sql
        assert "CREATE TABLE IF NOT EXISTS topic_sentiment_summary" in executed_sql
        assert conn.commit.called

    def test_init_propagates_db_error(self):
        fake_psycopg2 = MagicMock()
        fake_psycopg2.connect.side_effect = Exception("boom")
        with patch.object(mod, "psycopg2", fake_psycopg2):
            with pytest.raises(Exception, match="boom"):
                SentimentTrendAnalyzer(
                    snowflake_account="acct",
                    snowflake_user="u",
                    snowflake_password="p",
                    sentiment_analyzer=MagicMock(),
                    topic_extractor=MagicMock(),
                )

    def test_conn_params_built(self, analyzer):
        assert analyzer.conn_params["account"] == "acct"
        assert analyzer.conn_params["warehouse"] == "ANALYTICS_WH"
        assert analyzer.conn_params["database"] == "NEURONEWS"


# --------------------------------------------------------------------------
# _fetch_sentiment_data  (both topic and all-topics branches + parsing)
# --------------------------------------------------------------------------
class TestFetchSentimentData:
    @pytest.mark.asyncio
    async def test_fetch_specific_topic_parses_rows(self, analyzer):
        rows = [
            ("id1", "Title", "Content", datetime(2026, 1, 10).date(),
             "positive", 0.6, 0.9, "tech", ["ai"]),
        ]
        desc = [(c,) for c in (
            "id", "title", "content", "publish_date", "sentiment_label",
            "sentiment_score", "sentiment_confidence", "topic", "keywords")]
        cursor = _make_cursor(fetchall=rows, description=desc)
        fake_psycopg2, _ = _make_psycopg2(cursor)
        with patch.object(mod, "psycopg2", fake_psycopg2):
            result = await analyzer._fetch_sentiment_data(
                "tech", datetime(2026, 1, 1), datetime(2026, 1, 31))
        assert len(result) == 1
        assert result[0]["id"] == "id1"
        assert result[0]["topic"] == "tech"
        assert result[0]["sentiment_score"] == 0.6
        # specific-topic branch passes 3 params (topic, start, end)
        sql, params = cursor.execute.call_args.args
        assert "kt.topic = %s" in sql
        assert params == ("tech", datetime(2026, 1, 1).date(), datetime(2026, 1, 31).date())

    @pytest.mark.asyncio
    async def test_fetch_all_topics_branch(self, analyzer):
        cursor = _make_cursor(fetchall=[], description=[("topic",)])
        fake_psycopg2, _ = _make_psycopg2(cursor)
        with patch.object(mod, "psycopg2", fake_psycopg2):
            result = await analyzer._fetch_sentiment_data(
                None, datetime(2026, 1, 1), datetime(2026, 1, 31))
        assert result == []
        sql, params = cursor.execute.call_args.args
        # all-topics branch must NOT filter by topic and passes 2 params
        assert "kt.topic = %s" not in sql
        assert len(params) == 2

    @pytest.mark.asyncio
    async def test_fetch_returns_empty_on_error(self, analyzer):
        fake_psycopg2 = MagicMock()
        fake_psycopg2.connect.side_effect = Exception("db down")
        with patch.object(mod, "psycopg2", fake_psycopg2):
            result = await analyzer._fetch_sentiment_data(
                "tech", datetime(2026, 1, 1), datetime(2026, 1, 31))
        assert result == []


# --------------------------------------------------------------------------
# _store_trend_data / _store_alerts (execute_batch + commit)
# --------------------------------------------------------------------------
class TestStore:
    @pytest.mark.asyncio
    async def test_store_trend_data_noop_when_empty(self, analyzer):
        fake_psycopg2 = MagicMock()
        with patch.object(mod, "psycopg2", fake_psycopg2):
            await analyzer._store_trend_data([])
        assert not fake_psycopg2.connect.called

    @pytest.mark.asyncio
    async def test_store_trend_data_calls_execute_batch(self, analyzer):
        cursor = _make_cursor()
        fake_psycopg2, conn = _make_psycopg2(cursor)
        point = SentimentTrendPoint(
            date=datetime(2026, 1, 15), topic="tech", sentiment_score=0.5,
            sentiment_label="positive", confidence=0.9, article_count=2,
            source_articles=["a", "b"], metadata={"k": "v"})
        with patch.object(mod, "psycopg2", fake_psycopg2), \
                patch.object(mod, "execute_batch") as eb, \
                patch.object(mod, "Json", lambda x: x):
            await analyzer._store_trend_data([point])
        assert eb.called
        # second positional arg of execute_batch is the data list (one tuple)
        data_arg = eb.call_args.args[2]
        assert len(data_arg) == 1
        assert data_arg[0][0] == "tech"
        assert conn.commit.called

    @pytest.mark.asyncio
    async def test_store_trend_data_raises_on_error(self, analyzer):
        cursor = _make_cursor()
        fake_psycopg2, _ = _make_psycopg2(cursor)
        point = SentimentTrendPoint(
            date=datetime(2026, 1, 15), topic="tech", sentiment_score=0.5,
            sentiment_label="positive", confidence=0.9, article_count=1,
            source_articles=["a"], metadata={})
        with patch.object(mod, "psycopg2", fake_psycopg2), \
                patch.object(mod, "execute_batch", side_effect=Exception("write fail")), \
                patch.object(mod, "Json", lambda x: x):
            with pytest.raises(Exception, match="write fail"):
                await analyzer._store_trend_data([point])

    @pytest.mark.asyncio
    async def test_store_alerts_noop_when_empty(self, analyzer):
        fake_psycopg2 = MagicMock()
        with patch.object(mod, "psycopg2", fake_psycopg2):
            await analyzer._store_alerts([])
        assert not fake_psycopg2.connect.called

    @pytest.mark.asyncio
    async def test_store_alerts_calls_execute_batch(self, analyzer):
        cursor = _make_cursor()
        fake_psycopg2, conn = _make_psycopg2(cursor)
        alert = analyzer._create_alert(
            topic="tech", alert_type="significant_shift",
            current_sentiment=0.6, previous_sentiment=0.1,
            change_magnitude=0.5, change_percentage=500.0,
            time_window="7d", affected_articles=["a1"])
        with patch.object(mod, "psycopg2", fake_psycopg2), \
                patch.object(mod, "execute_batch") as eb, \
                patch.object(mod, "Json", lambda x: x):
            await analyzer._store_alerts([alert])
        assert eb.called
        data_arg = eb.call_args.args[2]
        assert data_arg[0][0] == alert.alert_id
        assert conn.commit.called


# --------------------------------------------------------------------------
# _create_alert severity branches + description direction
# --------------------------------------------------------------------------
class TestCreateAlertBranches:
    def test_severity_critical(self, analyzer):
        a = analyzer._create_alert(
            topic="t", alert_type="significant_shift",
            current_sentiment=0.7, previous_sentiment=0.0,
            change_magnitude=0.7, change_percentage=10.0,
            time_window="7d", affected_articles=["x"])
        assert a.severity == "critical"
        assert "improved" in a.description

    def test_severity_high(self, analyzer):
        a = analyzer._create_alert(
            topic="t", alert_type="significant_shift",
            current_sentiment=0.0, previous_sentiment=0.5,
            change_magnitude=0.45, change_percentage=10.0,
            time_window="7d", affected_articles=["x"])
        assert a.severity == "high"
        assert "declined" in a.description

    def test_severity_medium_and_low(self, analyzer):
        med = analyzer._create_alert(
            topic="t", alert_type="significant_shift",
            current_sentiment=0.3, previous_sentiment=0.0,
            change_magnitude=0.25, change_percentage=10.0,
            time_window="7d", affected_articles=["x"])
        assert med.severity == "medium"
        low = analyzer._create_alert(
            topic="t", alert_type="significant_shift",
            current_sentiment=0.1, previous_sentiment=0.0,
            change_magnitude=0.1, change_percentage=10.0,
            time_window="7d", affected_articles=["x"])
        assert low.severity == "low"

    def test_confidence_bounds(self, analyzer):
        # huge affected_articles list -> confidence capped at 0.95
        a = analyzer._create_alert(
            topic="t", alert_type="significant_shift",
            current_sentiment=0.9, previous_sentiment=0.0,
            change_magnitude=0.9, change_percentage=10.0,
            time_window="7d", affected_articles=["x"] * 200)
        assert a.confidence == 0.95


# --------------------------------------------------------------------------
# get_active_alerts (row -> TrendAlert parsing + filters)
# --------------------------------------------------------------------------
class TestGetActiveAlerts:
    @pytest.mark.asyncio
    async def test_parses_rows_into_alerts(self, analyzer):
        triggered = datetime(2026, 1, 10, tzinfo=timezone.utc)
        rows = [
            ("alert_1", "tech", "significant_shift", "high",
             0.8, 0.2, 0.6, 300.0, 0.9, "7d", triggered,
             "desc", ["a1"], {"m": 1}),
        ]
        cursor = _make_cursor(fetchall=rows)
        fake_psycopg2, _ = _make_psycopg2(cursor)
        with patch.object(mod, "psycopg2", fake_psycopg2):
            alerts = await analyzer.get_active_alerts(
                topic="tech", severity="high", limit=10)
        assert len(alerts) == 1
        a = alerts[0]
        assert isinstance(a, TrendAlert)
        assert a.alert_id == "alert_1"
        assert a.topic == "tech"
        assert a.severity == "high"
        assert a.affected_articles == ["a1"]
        assert a.metadata == {"m": 1}
        # filters appended both topic and severity plus limit -> 3 params
        _, params = cursor.execute.call_args.args
        assert params == ["tech", "high", 10]

    @pytest.mark.asyncio
    async def test_no_filters_only_limit_param(self, analyzer):
        cursor = _make_cursor(fetchall=[])
        fake_psycopg2, _ = _make_psycopg2(cursor)
        with patch.object(mod, "psycopg2", fake_psycopg2):
            alerts = await analyzer.get_active_alerts(limit=5)
        assert alerts == []
        _, params = cursor.execute.call_args.args
        assert params == [5]

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self, analyzer):
        fake_psycopg2 = MagicMock()
        fake_psycopg2.connect.side_effect = Exception("nope")
        with patch.object(mod, "psycopg2", fake_psycopg2):
            alerts = await analyzer.get_active_alerts()
        assert alerts == []

    @pytest.mark.asyncio
    async def test_none_articles_and_metadata_defaulted(self, analyzer):
        triggered = datetime(2026, 1, 10, tzinfo=timezone.utc)
        rows = [
            ("alert_2", "pol", "trend_reversal", "medium",
             -0.5, 0.3, 0.8, 266.7, 0.85, "7d", triggered,
             "d", None, None),
        ]
        cursor = _make_cursor(fetchall=rows)
        fake_psycopg2, _ = _make_psycopg2(cursor)
        with patch.object(mod, "psycopg2", fake_psycopg2):
            alerts = await analyzer.get_active_alerts()
        assert alerts[0].affected_articles == []
        assert alerts[0].metadata == {}


# --------------------------------------------------------------------------
# _store_topic_summary + update_topic_summaries
# --------------------------------------------------------------------------
class TestTopicSummaries:
    @pytest.mark.asyncio
    async def test_store_topic_summary_executes_upsert(self, analyzer):
        cursor = _make_cursor()
        fake_psycopg2, conn = _make_psycopg2(cursor)
        summary = TopicTrendSummary(
            topic="tech",
            time_range=(datetime(2026, 1, 1), datetime(2026, 1, 31)),
            current_sentiment=0.5, average_sentiment=0.4,
            sentiment_volatility=0.1, trend_direction="increasing",
            trend_strength=0.8, significant_changes=[],
            data_points=[MagicMock()], statistical_summary={"x": 1})
        with patch.object(mod, "psycopg2", fake_psycopg2), \
                patch.object(mod, "Json", lambda x: x):
            await analyzer._store_topic_summary(summary)
        assert cursor.execute.called
        sql, params = cursor.execute.call_args.args
        assert "topic_sentiment_summary" in sql
        assert params[0] == "tech"
        assert params[6] == 1  # data_points_count = len(data_points)
        assert conn.commit.called

    @pytest.mark.asyncio
    async def test_store_topic_summary_swallows_error(self, analyzer):
        # _store_topic_summary logs but does not re-raise
        fake_psycopg2 = MagicMock()
        fake_psycopg2.connect.side_effect = Exception("x")
        summary = TopicTrendSummary(
            topic="tech",
            time_range=(datetime(2026, 1, 1), datetime(2026, 1, 31)),
            current_sentiment=0.5, average_sentiment=0.4,
            sentiment_volatility=0.1, trend_direction="stable",
            trend_strength=0.0, significant_changes=[],
            data_points=[], statistical_summary={})
        with patch.object(mod, "psycopg2", fake_psycopg2):
            await analyzer._store_topic_summary(summary)  # no raise

    @pytest.mark.asyncio
    async def test_update_topic_summaries_iterates_topics(self, analyzer):
        cursor = _make_cursor(fetchall=[("tech",), ("politics",)])
        fake_psycopg2, _ = _make_psycopg2(cursor)
        fake_summary = MagicMock()
        with patch.object(mod, "psycopg2", fake_psycopg2), \
                patch.object(analyzer, "get_topic_trend_summary",
                             return_value=fake_summary) as gts, \
                patch.object(analyzer, "_store_topic_summary") as sts:
            # AsyncMock-like: make the patched coroutines awaitable
            async def _gts(topic):
                return fake_summary
            async def _sts(summary):
                return None
            gts.side_effect = _gts
            sts.side_effect = _sts
            await analyzer.update_topic_summaries()
        assert gts.call_count == 2
        assert sts.call_count == 2


# --------------------------------------------------------------------------
# Async orchestration: analyze_historical_trends / generate_sentiment_alerts
# --------------------------------------------------------------------------
class TestOrchestration:
    @pytest.mark.asyncio
    async def test_analyze_historical_trends_no_data(self, analyzer):
        async def _empty(topic, start, end):
            return []
        with patch.object(analyzer, "_fetch_sentiment_data", side_effect=_empty):
            out = await analyzer.analyze_historical_trends(topic="tech")
        assert out == []

    @pytest.mark.asyncio
    async def test_analyze_historical_trends_skips_insufficient(self, analyzer):
        # only 2 points for a topic; min_articles_for_trend is 5 -> skipped
        data = [datapoint(topic="tech", _id=f"a{i}") for i in range(2)]

        async def _fetch(topic, start, end):
            return data
        with patch.object(analyzer, "_fetch_sentiment_data", side_effect=_fetch):
            out = await analyzer.analyze_historical_trends(topic="tech")
        assert out == []

    @pytest.mark.asyncio
    async def test_analyze_historical_trends_full_path(self, analyzer):
        # 6 articles across distinct days -> >= min_articles, trend computed
        data = [
            datapoint(topic="tech", date=datetime(2026, 1, 10 + i).date(),
                      score=0.1 * i, _id=f"a{i}")
            for i in range(6)
        ]

        async def _fetch(topic, start, end):
            return data

        async def _store(points):
            return None

        with patch.object(analyzer, "_fetch_sentiment_data", side_effect=_fetch), \
                patch.object(analyzer, "_store_trend_data", side_effect=_store):
            out = await analyzer.analyze_historical_trends(
                topic="tech", time_granularity="daily")
        assert len(out) == 1
        summary = out[0]
        assert isinstance(summary, TopicTrendSummary)
        assert summary.topic == "tech"
        assert summary.trend_direction in ("increasing", "decreasing", "stable")
        assert len(summary.data_points) == 6
        assert "total_articles" in summary.statistical_summary

    @pytest.mark.asyncio
    async def test_analyze_historical_trends_default_dates(self, analyzer):
        captured = {}

        async def _fetch(topic, start, end):
            captured["start"] = start
            captured["end"] = end
            return []
        with patch.object(analyzer, "_fetch_sentiment_data", side_effect=_fetch):
            await analyzer.analyze_historical_trends(topic="tech")
        # default window = trend_window_days (30)
        delta = captured["end"] - captured["start"]
        assert delta.days == analyzer.config["trend_window_days"]

    @pytest.mark.asyncio
    async def test_generate_sentiment_alerts_no_data(self, analyzer):
        async def _empty(topic, start, end):
            return []
        with patch.object(analyzer, "_fetch_sentiment_data", side_effect=_empty):
            out = await analyzer.generate_sentiment_alerts(topic="tech")
        assert out == []

    @pytest.mark.asyncio
    async def test_generate_sentiment_alerts_produces_and_stores(self, analyzer):
        today = datetime.now(timezone.utc).date()
        # previous period strongly negative, current period strongly positive
        data = [
            datapoint(topic="tech", date=today - timedelta(days=12),
                      score=-0.6, _id="p1"),
            datapoint(topic="tech", date=today - timedelta(days=11),
                      score=-0.5, _id="p2"),
            datapoint(topic="tech", date=today - timedelta(days=2),
                      score=0.6, _id="c1"),
            datapoint(topic="tech", date=today - timedelta(days=1),
                      score=0.7, _id="c2"),
            datapoint(topic="tech", date=today,
                      score=0.65, _id="c3"),
        ]

        async def _fetch(topic, start, end):
            return data

        stored = {}

        async def _store(alerts):
            stored["alerts"] = alerts

        with patch.object(analyzer, "_fetch_sentiment_data", side_effect=_fetch), \
                patch.object(analyzer, "_store_alerts", side_effect=_store):
            out = await analyzer.generate_sentiment_alerts(
                topic="tech", lookback_days=7)
        assert len(out) >= 1
        types = {a.alert_type for a in out}
        # negative->positive crossing 0.1 magnitude triggers shift + reversal
        assert "significant_shift" in types
        assert all(isinstance(a, TrendAlert) for a in out)
        # alerts were forwarded to _store_alerts
        assert stored["alerts"] == out

    @pytest.mark.asyncio
    async def test_get_topic_trend_summary_returns_first(self, analyzer):
        fake_summary = MagicMock(spec=TopicTrendSummary)

        async def _analyze(topic, start_date, end_date):
            return [fake_summary]
        with patch.object(analyzer, "analyze_historical_trends",
                          side_effect=_analyze):
            res = await analyzer.get_topic_trend_summary("tech", days=15)
        assert res is fake_summary

    @pytest.mark.asyncio
    async def test_get_topic_trend_summary_none_when_empty(self, analyzer):
        async def _analyze(topic, start_date, end_date):
            return []
        with patch.object(analyzer, "analyze_historical_trends",
                          side_effect=_analyze):
            res = await analyzer.get_topic_trend_summary("tech")
        assert res is None


# --------------------------------------------------------------------------
# _detect_sentiment_alerts edge: single-period (no comparison) returns none
# --------------------------------------------------------------------------
class TestDetectEdge:
    @pytest.mark.asyncio
    async def test_no_previous_period_returns_empty(self, analyzer):
        today = datetime.now(timezone.utc).date()
        # all data in current period only
        data = [
            datapoint(topic="tech", date=today - timedelta(days=1), score=0.5),
            datapoint(topic="tech", date=today, score=0.6),
        ]
        out = await analyzer._detect_sentiment_alerts("tech", data, 7)
        assert out == []
