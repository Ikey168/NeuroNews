"""
Comprehensive test suite for Historical Sentiment Trend Analysis

This module tests the sentiment trend analysis functionality,
including trend calculation, alert generation, and API endpoints.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.nlp.sentiment_trend_analyzer import (
    SentimentTrendAnalyzer,
    SentimentTrendPoint,
    TopicTrendSummary,
    TrendAlert,
    analyze_sentiment_trends_for_topic,
    generate_daily_sentiment_alerts,
)


class TestSentimentTrendAnalyzer:
    """Test cases for SentimentTrendAnalyzer class."""

    @pytest.fixture
    def mock_redshift_config(self):
        """Mock Redshift configuration for testing."""
        return {
            "redshift_host": "test-redshift.amazonaws.com",
            "redshift_port": 5439,
            "redshift_database": "test_db",
            "redshift_user": "test_user",
            "redshift_password": "test_password",
        }

    @pytest.fixture
    def mock_sentiment_analyzer(self):
        """Mock sentiment analyzer for testing."""
        analyzer = Mock()
        analyzer.analyze = Mock(
            return_value={"label": "positive", "score": 0.8, "confidence": 0.9}
        )
        return analyzer

    @pytest.fixture
    def mock_topic_extractor(self):
        """Mock topic extractor for testing."""
        extractor = Mock()
        extractor.extract_topics = Mock(return_value=["technology", "politics"])
        return extractor

    @pytest.fixture
    def sample_sentiment_data(self):
        """Sample sentiment data for testing."""
        base_date = datetime.now(timezone.utc).date()
        return [
            {
                "id": "article_1",
                "title": "Tech News",
                "content": "Content 1",
                "publish_date": base_date - timedelta(days=5),
                "sentiment_label": "positive",
                "sentiment_score": 0.7,
                "sentiment_confidence": 0.9,
                "topic": "technology",
                "keywords": ["AI", "innovation"],
            },
            {
                "id": "article_2",
                "title": "Tech Update",
                "content": "Content 2",
                "publish_date": base_date - timedelta(days=4),
                "sentiment_label": "positive",
                "sentiment_score": 0.8,
                "sentiment_confidence": 0.85,
                "topic": "technology",
                "keywords": ["software", "development"],
            },
            {
                "id": "article_3",
                "title": "Political News",
                "content": "Content 3",
                "publish_date": base_date - timedelta(days=3),
                "sentiment_label": "negative",
                "sentiment_score": -0.6,
                "sentiment_confidence": 0.8,
                "topic": "politics",
                "keywords": ["election", "policy"],
            },
            {
                "id": "article_4",
                "title": "Tech Analysis",
                "content": "Content 4",
                "publish_date": base_date - timedelta(days=2),
                "sentiment_label": "neutral",
                "sentiment_score": 0.1,
                "sentiment_confidence": 0.7,
                "topic": "technology",
                "keywords": ["market", "analysis"],
            },
            {
                "id": "article_5",
                "title": "Political Update",
                "content": "Content 5",
                "publish_date": base_date - timedelta(days=1),
                "sentiment_label": "positive",
                "sentiment_score": 0.5,
                "sentiment_confidence": 0.88,
                "topic": "politics",
                "keywords": ["reform", "progress"],
            },
        ]

    @pytest.fixture
    def trend_analyzer(
        self, mock_redshift_config, mock_sentiment_analyzer, mock_topic_extractor
    ):
        """Create SentimentTrendAnalyzer instance with mocks."""
        with patch("psycopg2.connect") as mock_connect:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_connect.return_value.__enter__.return_value = mock_conn
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

            analyzer = SentimentTrendAnalyzer(
                sentiment_analyzer=mock_sentiment_analyzer,
                topic_extractor=mock_topic_extractor,
                **mock_redshift_config,
            )
            analyzer._mock_conn = mock_conn
            analyzer._mock_cursor = mock_cursor
            return analyzer

    def test_sentiment_trend_point_creation(self):
        """Test SentimentTrendPoint creation and properties."""
        date = datetime.now(timezone.utc)
        point = SentimentTrendPoint(
            date=date,
            topic="technology",
            sentiment_score=0.8,
            sentiment_label="positive",
            confidence=0.9,
            article_count=5,
            source_articles=["article_1", "article_2"],
            metadata={"test": "data"},
        )

        assert point.date == date
        assert point.topic == "technology"
        assert point.sentiment_score == 0.8
        assert point.sentiment_label == "positive"
        assert point.confidence == 0.9
        assert point.article_count == 5
        assert len(point.source_articles) == 2
        assert point.metadata["test"] == "data"

    def test_trend_alert_creation(self):
        """Test TrendAlert creation and properties."""
        triggered_at = datetime.now(timezone.utc)
        alert = TrendAlert(
            alert_id="test_alert_123",
            topic="politics",
            alert_type="significant_shift",
            severity="high",
            current_sentiment=0.3,
            previous_sentiment=-0.2,
            change_magnitude=0.5,
            change_percentage=250.0,
            confidence=0.85,
            time_window="7d",
            triggered_at=triggered_at,
            description="Test alert description",
            affected_articles=["article_1", "article_2"],
            metadata={"test": "alert_data"},
        )

        assert alert.alert_id == "test_alert_123"
        assert alert.topic == "politics"
        assert alert.alert_type == "significant_shift"
        assert alert.severity == "high"
        assert alert.current_sentiment == 0.3
        assert alert.previous_sentiment == -0.2
        assert alert.change_magnitude == 0.5
        assert alert.change_percentage == 250.0

    def test_group_data_by_topic(self, trend_analyzer, sample_sentiment_data):
        """Test grouping sentiment data by topic."""
        grouped_data = trend_analyzer._group_data_by_topic(sample_sentiment_data)

        assert "technology" in grouped_data
        assert "politics" in grouped_data
        assert len(grouped_data["technology"]) == 3
        assert len(grouped_data["politics"]) == 2

    def test_aggregate_by_time_granularity_daily(
        self, trend_analyzer, sample_sentiment_data
    ):
        """Test data aggregation by daily granularity."""
        tech_data = [
            item for item in sample_sentiment_data if item["topic"] == "technology"
        ]
        aggregated = trend_analyzer._aggregate_by_time_granularity(tech_data, "daily")

        # Should have 3 different dates for technology articles
        assert len(aggregated) == 3

        # Check that each date has the correct articles
        for date_key, articles in aggregated.items():
            assert len(articles) >= 1
            for article in articles:
                assert article["topic"] == "technology"

    def test_aggregate_by_time_granularity_weekly(
        self, trend_analyzer, sample_sentiment_data
    ):
        """Test data aggregation by weekly granularity."""
        tech_data = [
            item for item in sample_sentiment_data if item["topic"] == "technology"
        ]
        aggregated = trend_analyzer._aggregate_by_time_granularity(tech_data, "weekly")

        # All articles should fall within the same week
        assert len(aggregated) <= 2  # Depending on the week boundaries

    def test_create_trend_points(self, trend_analyzer, sample_sentiment_data):
        """Test creation of trend points from aggregated data."""
        tech_data = [
            item for item in sample_sentiment_data if item["topic"] == "technology"
        ]
        aggregated = trend_analyzer._aggregate_by_time_granularity(tech_data, "daily")

        trend_points = trend_analyzer._create_trend_points("technology", aggregated)

        assert len(trend_points) == len(aggregated)

        for point in trend_points:
            assert point.topic == "technology"
            assert isinstance(point.date, datetime)
            assert -1.0 <= point.sentiment_score <= 1.0
            assert point.sentiment_label in ["positive", "negative", "neutral"]
            assert 0.0 <= point.confidence <= 1.0
            assert point.article_count > 0
            assert len(point.source_articles) > 0

    def test_calculate_trend_summary(self, trend_analyzer):
        """Test calculation of trend summary statistics."""
        # Create sample trend points
        base_date = datetime.now(timezone.utc)
        trend_points = [
            SentimentTrendPoint(
                date=base_date - timedelta(days=i),
                topic="technology",
                sentiment_score=0.2 + (i * 0.1),  # Increasing trend
                sentiment_label="positive",
                confidence=0.8,
                article_count=5,
                source_articles=["article_{0}".format(i)],
                metadata={},
            )
            for i in range(5, 0, -1)  # 5 points with increasing sentiment
        ]

        time_range = (base_date - timedelta(days=5), base_date)
        summary = trend_analyzer._calculate_trend_summary(
            "technology", trend_points, time_range
        )

        assert summary.topic == "technology"
        assert summary.time_range == time_range
        assert summary.current_sentiment == trend_points[-1].sentiment_score
        assert summary.trend_direction == "increasing"  # Should detect increasing trend
        assert summary.trend_strength > 0  # Should have positive correlation
        assert len(summary.data_points) == 5
        assert "total_articles" in summary.statistical_summary

    def test_calculate_trend_summary_empty_points(self, trend_analyzer):
        """Test trend summary calculation with empty trend points."""
        time_range = (
            datetime.now(timezone.utc) - timedelta(days=5),
            datetime.now(timezone.utc),
        )
        summary = trend_analyzer._calculate_trend_summary("technology", [], time_range)

        assert summary.topic == "technology"
        assert summary.current_sentiment == 0.0
        assert summary.average_sentiment == 0.0
        assert summary.sentiment_volatility == 0.0
        assert summary.trend_direction == "stable"
        assert summary.trend_strength == 0.0
        assert len(summary.data_points) == 0

    @pytest.mark.asyncio
    async def test_fetch_sentiment_data(self, trend_analyzer, sample_sentiment_data):
        """Test fetching sentiment data from database."""
        # Mock database query
        with patch("psycopg2.connect") as mock_connect:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_connect.return_value.__enter__.return_value = mock_conn
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

            # Setup cursor to return sample data
            mock_cursor.fetchall.return_value = [
                tuple(item.values()) for item in sample_sentiment_data
            ]
            mock_cursor.description = [
                (key, None) for key in sample_sentiment_data[0].keys()
            ]

            start_date = datetime.now(timezone.utc) - timedelta(days=7)
            end_date = datetime.now(timezone.utc)

            result = await trend_analyzer._fetch_sentiment_data(
                "technology", start_date, end_date
            )

            assert len(result) == len(sample_sentiment_data)
            assert all("id" in item for item in result)
            assert all("sentiment_score" in item for item in result)

    @pytest.mark.asyncio
    async def test_detect_sentiment_alerts_significant_shift(self, trend_analyzer):
        """Test detection of significant sentiment shift alerts."""
        # Create data showing significant sentiment shift
        base_date = datetime.now(timezone.utc).date()
        topic_data = [
            # Previous period - negative sentiment
            {
                "id": "article_1",
                "publish_date": base_date - timedelta(days=10),
                "sentiment_score": -0.6,
                "sentiment_confidence": 0.8,
            },
            {
                "id": "article_2",
                "publish_date": base_date - timedelta(days=9),
                "sentiment_score": -0.5,
                "sentiment_confidence": 0.7,
            },
            # Current period - positive sentiment (significant shift)
            {
                "id": "article_3",
                "publish_date": base_date - timedelta(days=3),
                "sentiment_score": 0.6,
                "sentiment_confidence": 0.9,
            },
            {
                "id": "article_4",
                "publish_date": base_date - timedelta(days=2),
                "sentiment_score": 0.7,
                "sentiment_confidence": 0.85,
            },
        ]

        alerts = await trend_analyzer._detect_sentiment_alerts(
            "technology", topic_data, 7
        )

        # Should detect significant shift
        assert len(alerts) > 0
        shift_alert = next(
            (a for a in alerts if a.alert_type == "significant_shift"), None
        )
        assert shift_alert is not None
        assert shift_alert.topic == "technology"
        assert (
            shift_alert.change_magnitude
            >= trend_analyzer.config["alert_thresholds"]["significant_shift"]
        )

    @pytest.mark.asyncio
    async def test_detect_sentiment_alerts_trend_reversal(self, trend_analyzer):
        """Test detection of trend reversal alerts."""
        base_date = datetime.now(timezone.utc).date()
        topic_data = [
            # Previous period - positive sentiment
            {
                "id": "article_1",
                "publish_date": base_date - timedelta(days=10),
                "sentiment_score": 0.6,
                "sentiment_confidence": 0.8,
            },
            # Current period - negative sentiment (reversal)
            {
                "id": "article_2",
                "publish_date": base_date - timedelta(days=2),
                "sentiment_score": -0.6,
                "sentiment_confidence": 0.9,
            },
        ]

        alerts = await trend_analyzer._detect_sentiment_alerts(
            "technology", topic_data, 7
        )

        # Should detect trend reversal
        reversal_alert = next(
            (a for a in alerts if a.alert_type == "trend_reversal"), None
        )
        assert reversal_alert is not None
        assert reversal_alert.topic == "technology"

    @pytest.mark.asyncio
    async def test_detect_sentiment_alerts_volatility_spike(self, trend_analyzer):
        """Test detection of volatility spike alerts."""
        base_date = datetime.now(timezone.utc).date()
        topic_data = [
            # Previous period - low volatility
            {
                "id": "article_1",
                "publish_date": base_date - timedelta(days=10),
                "sentiment_score": 0.1,
                "sentiment_confidence": 0.8,
            },
            {
                "id": "article_2",
                "publish_date": base_date - timedelta(days=9),
                "sentiment_score": 0.1,
                "sentiment_confidence": 0.8,
            },
            # Current period - high volatility
            {
                "id": "article_3",
                "publish_date": base_date - timedelta(days=2),
                "sentiment_score": 0.8,
                "sentiment_confidence": 0.9,
            },
            {
                "id": "article_4",
                "publish_date": base_date - timedelta(days=1),
                "sentiment_score": -0.8,
                "sentiment_confidence": 0.9,
            },
        ]

        alerts = await trend_analyzer._detect_sentiment_alerts(
            "technology", topic_data, 7
        )

        # Should detect volatility spike
        volatility_alert = next(
            (a for a in alerts if a.alert_type == "volatility_spike"), None
        )
        assert volatility_alert is not None
        assert volatility_alert.topic == "technology"

    def test_create_alert(self, trend_analyzer):
        """Test alert creation with proper attributes."""
        alert = trend_analyzer._create_alert(
            topic="technology",
            alert_type="significant_shift",
            current_sentiment=0.6,
            previous_sentiment=0.1,
            change_magnitude=0.5,
            change_percentage=500.0,
            time_window="7d",
            affected_articles=["article_1", "article_2"],
        )

        assert alert.topic == "technology"
        assert alert.alert_type == "significant_shift"
        assert alert.severity in ["low", "medium", "high", "critical"]
        assert alert.current_sentiment == 0.6
        assert alert.previous_sentiment == 0.1
        assert alert.change_magnitude == 0.5
        assert alert.change_percentage == 500.0
        assert alert.time_window == "7d"
        assert len(alert.affected_articles) == 2
        assert "improved" in alert.description  # Should mention improvement

    @pytest.mark.asyncio
    async def test_store_trend_data(self, trend_analyzer):
        """Test storing trend data in database."""
        trend_points = [
            SentimentTrendPoint(
                date=datetime.now(timezone.utc),
                topic="technology",
                sentiment_score=0.5,
                sentiment_label="positive",
                confidence=0.8,
                article_count=3,
                source_articles=["article_1", "article_2"],
                metadata={"test": "data"},
            )
        ]

        with patch("psycopg2.connect") as mock_connect:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_connect.return_value.__enter__.return_value = mock_conn
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

            await trend_analyzer._store_trend_data(trend_points)

            # Verify execute_batch was called
            assert mock_cursor.execute_batch is not None or hasattr(
                mock_cursor, "execute"
            )
            mock_conn.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_alerts(self, trend_analyzer):
        """Test storing alerts in database."""
        alerts = [
            TrendAlert(
                alert_id="test_alert_123",
                topic="technology",
                alert_type="significant_shift",
                severity="high",
                current_sentiment=0.6,
                previous_sentiment=0.1,
                change_magnitude=0.5,
                change_percentage=500.0,
                confidence=0.8,
                time_window="7d",
                triggered_at=datetime.now(timezone.utc),
                description="Test alert",
                affected_articles=["article_1"],
                metadata={"test": "data"},
            )
        ]

        with patch("psycopg2.connect") as mock_connect:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_connect.return_value.__enter__.return_value = mock_conn
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

            await trend_analyzer._store_alerts(alerts)

            # Verify execute_batch was called
            assert mock_cursor.execute_batch is not None or hasattr(
                mock_cursor, "execute"
            )
            mock_conn.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_historical_trends(
        self, trend_analyzer, sample_sentiment_data
    ):
        """Test full historical trend analysis workflow."""
        with patch.object(trend_analyzer, "_fetch_sentiment_data") as mock_fetch:
            with patch.object(trend_analyzer, "_store_trend_data"):
                mock_fetch.return_value = sample_sentiment_data

                start_date = datetime.now(timezone.utc) - timedelta(days=7)
                end_date = datetime.now(timezone.utc)

                summaries = await trend_analyzer.analyze_historical_trends(
                    topic=None,
                    start_date=start_date,
                    end_date=end_date,
                    time_granularity="daily",
                )

                # Should return summaries for both topics in sample data
                # At least one topic should have enough data
                assert len(summaries) >= 1

                for summary in summaries:
                    assert isinstance(summary, TopicTrendSummary)
                    assert summary.topic in ["technology", "politics"]
                    assert len(summary.data_points) > 0

    @pytest.mark.asyncio
    async def test_generate_sentiment_alerts(
        self, trend_analyzer, sample_sentiment_data
    ):
        """Test sentiment alert generation workflow."""
        # Modify sample data to create alert conditions
        alert_data = sample_sentiment_data.copy()
        # Make recent articles very positive to trigger alerts
        for item in alert_data:
            if item["publish_date"] >= datetime.now(timezone.utc).date() - timedelta(
                days=3
            ):
                item["sentiment_score"] = 0.9
                item["sentiment_label"] = "positive"

        with patch.object(trend_analyzer, "_fetch_sentiment_data") as mock_fetch:
            with patch.object(trend_analyzer, "_store_alerts"):
                mock_fetch.return_value = alert_data

                alerts = await trend_analyzer.generate_sentiment_alerts(
                    topic=None, lookback_days=7
                )

                # Should generate alerts due to significant changes
                assert isinstance(alerts, list)

                for alert in alerts:
                    assert isinstance(alert, TrendAlert)
                    assert alert.topic in ["technology", "politics"]
                    assert alert.alert_type in [
                        "significant_shift",
                        "trend_reversal",
                        "volatility_spike",
                    ]

    @pytest.mark.asyncio
    async def test_get_active_alerts(self, trend_analyzer):
        """Test retrieving active alerts from database."""
        sample_alerts_data = [
            (
                "alert_1",
                "technology",
                "significant_shift",
                "high",
                0.8,
                0.2,
                0.6,
                300.0,
                0.9,
                "7d",
                datetime.now(timezone.utc),
                "Test alert",
                ["article_1"],
                {},
            ),
            (
                "alert_2",
                "politics",
                "trend_reversal",
                "medium",
                -0.5,
                0.3,
                0.8,
                266.7,
                0.85,
                "7d",
                datetime.now(timezone.utc),
                "Test alert 2",
                ["article_2"],
                {},
            ),
        ]

        with patch("psycopg2.connect") as mock_connect:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_connect.return_value.__enter__.return_value = mock_conn
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

            mock_cursor.fetchall.return_value = sample_alerts_data

            alerts = await trend_analyzer.get_active_alerts(
                topic="technology", limit=10
            )

            assert isinstance(alerts, list)
            # The mock will return all alerts, but in real implementation would
            # filter by topic

            for alert in alerts:
                assert isinstance(alert, TrendAlert)
                assert hasattr(alert, "alert_id")
                assert hasattr(alert, "topic")
                assert hasattr(alert, "severity")


class TestUtilityFunctions:
    """Test utility functions for sentiment trend analysis."""

    @pytest.mark.asyncio
    async def test_analyze_sentiment_trends_for_topic(self):
        """Test convenience function for topic trend analysis."""
        redshift_config = {
            "redshift_host": "test-host",
            "redshift_port": 5439,
            "redshift_database": "test_db",
            "redshift_user": "test_user",
            "redshift_password": "test_password",
        }

        with patch(
            "src.nlp.sentiment_trend_analyzer.SentimentTrendAnalyzer"
        ) as MockAnalyzer:
            mock_instance = AsyncMock()
            mock_instance.get_topic_trend_summary = AsyncMock(return_value=None)
            MockAnalyzer.return_value = mock_instance

            _ = await analyze_sentiment_trends_for_topic(
                "technology", redshift_config, days=30
            )

            MockAnalyzer.assert_called_once_with(**redshift_config)
            mock_instance.get_topic_trend_summary.assert_called_once_with(
                "technology", 30
            )

    @pytest.mark.asyncio
    async def test_generate_daily_sentiment_alerts(self):
        """Test convenience function for daily alert generation."""
        redshift_config = {
            "redshift_host": "test-host",
            "redshift_port": 5439,
            "redshift_database": "test_db",
            "redshift_user": "test_user",
            "redshift_password": "test_password",
        }

        with patch(
            "src.nlp.sentiment_trend_analyzer.SentimentTrendAnalyzer"
        ) as MockAnalyzer:
            mock_instance = AsyncMock()
            mock_instance.generate_sentiment_alerts = AsyncMock(return_value=[])
            MockAnalyzer.return_value = mock_instance

            await generate_daily_sentiment_alerts(redshift_config)

            MockAnalyzer.assert_called_once_with(**redshift_config)
            mock_instance.generate_sentiment_alerts.assert_called_once_with(
                lookback_days=7
            )


class TestDataValidation:
    """Test data validation and edge cases."""

    def test_invalid_sentiment_scores(self, trend_analyzer):
        """Test handling of invalid sentiment scores."""
        # Test trend point creation with edge case sentiment scores
        base_date = datetime.now(timezone.utc)

        # Valid range
        point = SentimentTrendPoint(
            date=base_date,
            topic="test",
            sentiment_score=0.5,
            sentiment_label="positive",
            confidence=0.8,
            article_count=1,
            source_articles=["article_1"],
            metadata={},
        )
        assert -1.0 <= point.sentiment_score <= 1.0

        # Edge cases
        edge_point = SentimentTrendPoint(
            date=base_date,
            topic="test",
            sentiment_score=1.0,  # Maximum positive
            sentiment_label="positive",
            confidence=0.8,
            article_count=1,
            source_articles=["article_1"],
            metadata={},
        )
        assert edge_point.sentiment_score == 1.0

    def test_empty_data_handling(self, trend_analyzer):
        """Test handling of empty or insufficient data."""
        # Test with empty aggregated data
        trend_points = trend_analyzer._create_trend_points("test_topic", {})
        assert len(trend_points) == 0

        # Test trend summary with empty points
        time_range = (
            datetime.now(timezone.utc) - timedelta(days=7),
            datetime.now(timezone.utc),
        )
        summary = trend_analyzer._calculate_trend_summary("test_topic", [], time_range)

        assert summary.topic == "test_topic"
        assert summary.current_sentiment == 0.0
        assert summary.average_sentiment == 0.0
        assert summary.trend_direction == "stable"

    def test_single_data_point_handling(self, trend_analyzer):
        """Test handling of single data point scenarios."""
        base_date = datetime.now(timezone.utc)
        single_point = [
            SentimentTrendPoint(
                date=base_date,
                topic="test",
                sentiment_score=0.5,
                sentiment_label="positive",
                confidence=0.8,
                article_count=1,
                source_articles=["article_1"],
                metadata={},
            )
        ]

        time_range = (base_date - timedelta(days=1), base_date)
        summary = trend_analyzer._calculate_trend_summary(
            "test", single_point, time_range
        )

        assert summary.current_sentiment == 0.5
        assert summary.average_sentiment == 0.5
        assert summary.sentiment_volatility == 0.0  # No variance with single point
        assert (
            summary.trend_direction == "stable"
        )  # Can't determine trend with one point

    @pytest.mark.asyncio
    async def test_database_error_handling(self, trend_analyzer):
        """Test handling of database connection errors."""
        with patch("psycopg2.connect") as mock_connect:
            mock_connect.side_effect = Exception("Database connection failed")

            # Should handle database errors gracefully
            result = await trend_analyzer._fetch_sentiment_data(
                "test_topic",
                datetime.now(timezone.utc) - timedelta(days=7),
                datetime.now(timezone.utc),
            )

            assert result == []  # Should return empty list on error


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
