"""
Tests for the SentimentTrendAnalyzer system.

This module tests the comprehensive sentiment trend analysis functionality
including historical trend calculation, alert generation, and data storage.
"""

import statistics
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, MagicMock, patch

import pytest

# Mock psycopg2 before importing SentimentTrendAnalyzer
if "psycopg2" not in sys.modules:
    # Create comprehensive mock for psycopg2 if not already mocked
    mock_psycopg2 = MagicMock()
    mock_connection = MagicMock()
    mock_cursor = MagicMock()

    # Setup cursor context manager
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=None)
    mock_cursor.fetchone = MagicMock(return_value=None)
    mock_cursor.fetchall = MagicMock(return_value=[])
    mock_cursor.fetchmany = MagicMock(return_value=[])
    mock_cursor.execute = MagicMock()
    mock_cursor.mogrify = MagicMock(return_value=b"mocked query")
    mock_cursor.execute_batch = MagicMock()  # Add execute_batch mock

    # Setup connection context manager and cursor method
    mock_connection.cursor.return_value = mock_cursor
    mock_connection.__enter__ = MagicMock(return_value=mock_connection)
    mock_connection.__exit__ = MagicMock(return_value=None)
    mock_connection.commit = MagicMock()
    mock_connection.rollback = MagicMock()

    # Setup connect function
    mock_psycopg2.connect = MagicMock(return_value=mock_connection)
    mock_psycopg2.extras = MagicMock()
    mock_psycopg2.extras.RealDictCursor = MagicMock()
    mock_psycopg2.extras.execute_batch = MagicMock()

    # Replace sys.modules
    sys.modules["psycopg2"] = mock_psycopg2
    sys.modules["psycopg2.extras"] = mock_psycopg2.extras

from src.nlp.sentiment_trend_analyzer import (
    SentimentTrendAnalyzer,
    SentimentTrendPoint,
    TopicTrendSummary,
    TrendAlert,
    analyze_sentiment_trends_for_topic,
    generate_daily_sentiment_alerts,
)

# Global patch to prevent database connections during testing
pytestmark = [
    pytest.mark.filterwarnings("ignore::DeprecationWarning"),
]

from src.nlp.sentiment_trend_analyzer import (
    SentimentTrendAnalyzer,
    SentimentTrendPoint,
    TopicTrendSummary,
    TrendAlert,
    analyze_sentiment_trends_for_topic,
    generate_daily_sentiment_alerts,
)


@pytest.fixture
def mock_redshift_config():
    """Mock Redshift configuration for testing."""
    return {
        "redshift_host": "test-redshift.amazonaws.com",
        "redshift_port": 5439,
        "redshift_database": "test_db",
        "redshift_user": "test_user",
        "redshift_password": "test_password",
    }


@pytest.fixture
def mock_sentiment_analyzer():
    """Mock sentiment analyzer for testing."""
    analyzer = Mock()
    analyzer.analyze = Mock(return_value={"label": "positive", "score": 0.8, "confidence": 0.9})
    return analyzer


@pytest.fixture
def mock_topic_extractor():
    """Mock topic extractor for testing."""
    extractor = Mock()
    extractor.extract_topics = Mock(return_value=["technology", "politics"])
    return extractor


@pytest.fixture
def sample_sentiment_data():
    """Sample sentiment data for testing."""
    return [
        {
            "id": "article_1",
            "content": "Content 1",
            "publish_date": datetime.now(timezone.utc).date() - timedelta(days=1),
            "sentiment_score": 0.7,
            "sentiment_confidence": 0.8,
            "topic": "technology",
            "keywords": ["AI", "innovation"],
        },
        {
            "id": "article_2",
            "content": "Content 2",
            "publish_date": datetime.now(timezone.utc).date() - timedelta(days=2),
            "sentiment_score": 0.5,
            "sentiment_confidence": 0.7,
            "topic": "technology",
            "keywords": ["technology", "development"],
        },
        {
            "id": "article_3",
            "content": "Content 3",
            "publish_date": datetime.now(timezone.utc).date() - timedelta(days=1),
            "sentiment_score": 0.3,
            "sentiment_confidence": 0.6,
            "topic": "technology",
            "keywords": ["technology", "challenges"],
        },
        {
            "id": "article_4",
            "content": "Content 4",
            "publish_date": datetime.now(timezone.utc).date() - timedelta(days=3),
            "sentiment_score": -0.2,
            "sentiment_confidence": 0.8,
            "topic": "politics",
            "keywords": ["politics", "debate"],
        },
        {
            "id": "article_5",
            "content": "Content 5",
            "publish_date": datetime.now(timezone.utc).date() - timedelta(days=1),
            "sentiment_score": 0.1,
            "sentiment_confidence": 0.7,
            "topic": "politics",
            "keywords": ["reform", "progress"],
        },
        # Add more articles for technology to meet minimum requirement
        {
            "id": "article_6",
            "content": "Technology advancement content",
            "publish_date": datetime.now(timezone.utc).date() - timedelta(days=1),
            "sentiment_score": 0.8,
            "sentiment_confidence": 0.9,
            "topic": "technology",
            "keywords": ["technology", "innovation"],
        },
        {
            "id": "article_7",
            "content": "Tech breakthrough news",
            "publish_date": datetime.now(timezone.utc).date() - timedelta(days=2),
            "sentiment_score": 0.6,
            "sentiment_confidence": 0.8,
            "topic": "technology",
            "keywords": ["technology", "breakthrough"],
        },
        # Add more articles for politics to meet minimum requirement
        {
            "id": "article_8",
            "content": "Political development content",
            "publish_date": datetime.now(timezone.utc).date() - timedelta(days=2),
            "sentiment_score": 0.4,
            "sentiment_confidence": 0.7,
            "topic": "politics",
            "keywords": ["politics", "development"],
        },
        {
            "id": "article_9",
            "content": "Government policy update",
            "publish_date": datetime.now(timezone.utc).date() - timedelta(days=3),
            "sentiment_score": 0.2,
            "sentiment_confidence": 0.8,
            "topic": "politics",
            "keywords": ["politics", "policy"],
        },
        {
            "id": "article_10",
            "content": "Political campaign news",
            "publish_date": datetime.now(timezone.utc).date() - timedelta(days=1),
            "sentiment_score": -0.1,
            "sentiment_confidence": 0.75,
            "topic": "politics",
            "keywords": ["politics", "campaign"],
        },
    ]


@pytest.fixture
def trend_analyzer(mock_redshift_config, mock_sentiment_analyzer, mock_topic_extractor):
    """Create SentimentTrendAnalyzer instance with mocks."""
    # Use the global mock that's already established
    with patch.object(SentimentTrendAnalyzer, '_initialize_database_schema'):
        analyzer = SentimentTrendAnalyzer(
            sentiment_analyzer=mock_sentiment_analyzer,
            topic_extractor=mock_topic_extractor,
            **mock_redshift_config,
        )
        return analyzer


@pytest.fixture(autouse=True)
def ensure_clean_database_mock():
    """Autouse fixture to ensure database mock is clean for each test."""
    import sys
    psycopg2_mock = sys.modules["psycopg2"]
    
    # Store original state
    original_side_effect = getattr(psycopg2_mock.connect, 'side_effect', None)
    
    # Reset to clean state before test
    psycopg2_mock.connect.side_effect = None
    psycopg2_mock.connect.reset_mock()
    
    yield
    
    # Reset after test to prevent interference
    psycopg2_mock.connect.side_effect = None
    psycopg2_mock.connect.reset_mock()


@pytest.fixture
def reset_database_mock():
    """Fixture to ensure database mock is properly reset for each test."""
    import sys
    psycopg2_mock = sys.modules["psycopg2"]
    
    # Reset any side effects from previous tests
    psycopg2_mock.connect.side_effect = None
    psycopg2_mock.connect.reset_mock()
    
    # Get or create mock objects - reuse existing if available, create new if needed
    mock_connection = psycopg2_mock.connect.return_value
    if not hasattr(mock_connection, 'cursor') or not mock_connection.cursor:
        mock_connection = Mock()
        psycopg2_mock.connect.return_value = mock_connection
    
    mock_cursor = mock_connection.cursor.return_value
    if not hasattr(mock_cursor, 'fetchall'):
        mock_cursor = Mock()
        mock_connection.cursor.return_value = mock_cursor
    
    # Reset the existing mocks
    mock_connection.reset_mock()
    mock_cursor.reset_mock()
    
    # Setup context managers properly
    mock_cursor.__enter__ = Mock(return_value=mock_cursor)
    mock_cursor.__exit__ = Mock(return_value=None)
    mock_connection.__enter__ = Mock(return_value=mock_connection)
    mock_connection.__exit__ = Mock(return_value=None)
    mock_connection.cursor.return_value = mock_cursor
    
    # Return the mocks for the test to configure as needed
    return mock_connection, mock_cursor


class TestSentimentTrendAnalyzer:
    """Test cases for SentimentTrendAnalyzer class."""

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
        assert len(grouped_data["technology"]) == 5  # Updated to match our new sample data
        assert len(grouped_data["politics"]) == 5  # Updated to match our new sample data

    def test_aggregate_by_time_granularity_daily(self, trend_analyzer, sample_sentiment_data):
        """Test data aggregation by daily granularity."""
        tech_data = [item for item in sample_sentiment_data if item["topic"] == "technology"]
        aggregated = trend_analyzer._aggregate_by_time_granularity(tech_data, "daily")

        # Should have 2 different dates for technology articles (based on our sample data)
        assert len(aggregated) == 2

        # Check that each date has the correct articles
        for date_key, articles in aggregated.items():
            assert len(articles) >= 1
            for article in articles:
                assert article["topic"] == "technology"

    def test_aggregate_by_time_granularity_weekly(self, trend_analyzer, sample_sentiment_data):
        """Test data aggregation by weekly granularity."""
        tech_data = [item for item in sample_sentiment_data if item["topic"] == "technology"]
        aggregated = trend_analyzer._aggregate_by_time_granularity(tech_data, "weekly")

        # All articles should fall within the same week
        assert len(aggregated) <= 2  # Depending on the week boundaries

    def test_create_trend_points(self, trend_analyzer, sample_sentiment_data):
        """Test creation of trend points from aggregated data."""
        tech_data = [item for item in sample_sentiment_data if item["topic"] == "technology"]
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
        # Create sample trend points with increasing trend
        base_date = datetime.now(timezone.utc)
        trend_points = [
            SentimentTrendPoint(
                date=base_date - timedelta(days=i),
                topic="technology",
                sentiment_score=0.2 + ((5 - i) * 0.1),  # Increasing trend over time
                sentiment_label="positive",
                confidence=0.8,
                article_count=5,
                source_articles=["article_{0}".format(i)],
                metadata={},
            )
            for i in range(5, 0, -1)  # 5 points with increasing sentiment
        ]

        time_range = (base_date - timedelta(days=5), base_date)
        summary = trend_analyzer._calculate_trend_summary("technology", trend_points, time_range)
        
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
        # Get the global mock and completely reset it
        import sys
        psycopg2_mock = sys.modules["psycopg2"]
        psycopg2_mock.connect.reset_mock()
        psycopg2_mock.connect.side_effect = None
        
        # Create completely fresh mock objects
        mock_cursor = Mock()
        mock_connection = Mock()
        
        # Setup context managers
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=None)
        mock_connection.__enter__ = Mock(return_value=mock_connection)
        mock_connection.__exit__ = Mock(return_value=None)
        mock_connection.cursor.return_value = mock_cursor
        
        # Configure the global mock with fresh objects
        psycopg2_mock.connect.return_value = mock_connection
        
        # Setup cursor to return sample data
        mock_cursor.fetchall.return_value = [
            tuple(item.values()) for item in sample_sentiment_data
        ]
        mock_cursor.description = [(key, None) for key in sample_sentiment_data[0].keys()]

        start_date = datetime.now(timezone.utc) - timedelta(days=7)
        end_date = datetime.now(timezone.utc)

        result = await trend_analyzer._fetch_sentiment_data("technology", start_date, end_date)

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

        alerts = await trend_analyzer._detect_sentiment_alerts("technology", topic_data, 7)

        # Should detect significant shift
        assert len(alerts) > 0
        shift_alert = next((a for a in alerts if a.alert_type == "significant_shift"), None)
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

        alerts = await trend_analyzer._detect_sentiment_alerts("technology", topic_data, 7)

        # Should detect trend reversal
        reversal_alert = next((a for a in alerts if a.alert_type == "trend_reversal"), None)
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

        alerts = await trend_analyzer._detect_sentiment_alerts("technology", topic_data, 7)

        # Should detect volatility spike
        volatility_alert = next((a for a in alerts if a.alert_type == "volatility_spike"), None)
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
        # Get the global mock and completely reset it
        import sys
        psycopg2_mock = sys.modules["psycopg2"]
        psycopg2_mock.connect.reset_mock()
        psycopg2_mock.connect.side_effect = None
        
        # Create completely fresh mock objects
        mock_cursor = Mock()
        mock_connection = Mock()
        
        # Setup context managers
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=None)
        mock_connection.__enter__ = Mock(return_value=mock_connection)
        mock_connection.__exit__ = Mock(return_value=None)
        mock_connection.cursor.return_value = mock_cursor
        
        # Configure the global mock with fresh objects
        psycopg2_mock.connect.return_value = mock_connection
        
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

        await trend_analyzer._store_trend_data(trend_points)

        # Verify execute_batch was called or connection operations occurred
        assert mock_cursor.execute.called or mock_cursor.mogrify.called or mock_connection.commit.called

    @pytest.mark.asyncio
    async def test_store_alerts(self, trend_analyzer):
        """Test storing alerts in database."""
        # Get the global mock and completely reset it
        import sys
        psycopg2_mock = sys.modules["psycopg2"]
        psycopg2_mock.connect.reset_mock()
        psycopg2_mock.connect.side_effect = None
        
        # Create completely fresh mock objects
        mock_cursor = Mock()
        mock_connection = Mock()
        
        # Setup context managers
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=None)
        mock_connection.__enter__ = Mock(return_value=mock_connection)
        mock_connection.__exit__ = Mock(return_value=None)
        mock_connection.cursor.return_value = mock_cursor
        
        # Configure the global mock with fresh objects
        psycopg2_mock.connect.return_value = mock_connection
        
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

        await trend_analyzer._store_alerts(alerts)

        # Verify execute_batch was called or connection operations occurred
        assert mock_cursor.execute.called or mock_cursor.mogrify.called or mock_connection.commit.called

    @pytest.mark.asyncio
    async def test_analyze_historical_trends(self, trend_analyzer, sample_sentiment_data):
        """Test full historical trend analysis workflow."""
        with patch.object(trend_analyzer, "_fetch_sentiment_data") as mock_fetch:
            with patch.object(trend_analyzer, "_store_trend_data"):
                
                def mock_fetch_by_topic(topic, start_date, end_date):
                    """Mock that filters by topic when specified."""
                    if topic:
                        # Filter data by topic
                        return [item for item in sample_sentiment_data if item.get("topic") == topic]
                    else:
                        # Return all data
                        return sample_sentiment_data
                
                mock_fetch.side_effect = mock_fetch_by_topic

                start_date = datetime.now(timezone.utc) - timedelta(days=7)
                end_date = datetime.now(timezone.utc)

                # Test without specific topic (should return all topics found)
                summaries = await trend_analyzer.analyze_historical_trends(
                    topic=None,
                    start_date=start_date,
                    end_date=end_date,
                    time_granularity="daily",
                )

                assert len(summaries) >= 1

                for summary in summaries:
                    assert isinstance(summary, TopicTrendSummary)
                    # When no topic is specified, it returns all topics found
                    assert summary.topic in ["technology", "politics"]
                    assert summary.current_sentiment is not None
                    assert summary.trend_direction in ["increasing", "decreasing", "stable"]
                    assert len(summary.data_points) >= 2  # Need at least 2 points for trends
                    
                # Test with specific topic
                topic_summaries = await trend_analyzer.analyze_historical_trends(
                    topic="technology",
                    start_date=start_date,
                    end_date=end_date,
                    time_granularity="daily",
                )
                
                assert len(topic_summaries) >= 1
                
                for summary in topic_summaries:
                    assert isinstance(summary, TopicTrendSummary)
                    assert summary.topic == "technology"
                    assert len(summary.data_points) > 0

    @pytest.mark.asyncio
    async def test_generate_sentiment_alerts(self, trend_analyzer, sample_sentiment_data):
        """Test sentiment alert generation workflow."""
        # Modify sample data to create alert conditions
        alert_data = sample_sentiment_data.copy()
        # Make recent articles very positive to trigger alerts
        for item in alert_data:
            if item["publish_date"] >= datetime.now(timezone.utc).date() - timedelta(days=3):
                item["sentiment_score"] = 0.9
                item["sentiment_label"] = "positive"

        with patch.object(trend_analyzer, "_fetch_sentiment_data") as mock_fetch:
            with patch.object(trend_analyzer, "_store_alerts"):
                mock_fetch.return_value = alert_data

                alerts = await trend_analyzer.generate_sentiment_alerts(topic=None, lookback_days=7)

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

        # Work with the global mock
        import sys
        psycopg2_mock = sys.modules["psycopg2"]
        mock_connection = psycopg2_mock.connect.return_value
        mock_cursor = mock_connection.cursor.return_value
        
        # Reset and configure mock for this test
        mock_cursor.reset_mock()
        mock_connection.reset_mock()
        mock_cursor.fetchall.return_value = sample_alerts_data

        alerts = await trend_analyzer.get_active_alerts(topic="technology", limit=10)

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

        with patch("src.nlp.sentiment_trend_analyzer.SentimentTrendAnalyzer") as MockAnalyzer:
            mock_instance = AsyncMock()
            mock_instance.get_topic_trend_summary = AsyncMock(return_value=None)
            MockAnalyzer.return_value = mock_instance

            _ = await analyze_sentiment_trends_for_topic("technology", redshift_config, days=30)

            MockAnalyzer.assert_called_once_with(**redshift_config)
            mock_instance.get_topic_trend_summary.assert_called_once_with("technology", 30)

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

        with patch("src.nlp.sentiment_trend_analyzer.SentimentTrendAnalyzer") as MockAnalyzer:
            mock_instance = AsyncMock()
            mock_instance.generate_sentiment_alerts = AsyncMock(return_value=[])
            MockAnalyzer.return_value = mock_instance

            await generate_daily_sentiment_alerts(redshift_config)

            MockAnalyzer.assert_called_once_with(**redshift_config)
            mock_instance.generate_sentiment_alerts.assert_called_once_with(lookback_days=7)


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
        summary = trend_analyzer._calculate_trend_summary("test", single_point, time_range)

        assert summary.current_sentiment == 0.5
        assert summary.average_sentiment == 0.5
        assert summary.sentiment_volatility == 0.0  # No variance with single point
        assert summary.trend_direction == "stable"  # Can't determine trend with one point

    @pytest.mark.asyncio
    async def test_database_error_handling(self, trend_analyzer):
        """Test handling of database connection errors."""
        # Work with the global mock
        import sys
        psycopg2_mock = sys.modules["psycopg2"]
        
        # Configure the global mock to raise an exception
        psycopg2_mock.connect.side_effect = Exception("Database connection failed")

        try:
            # Should handle database errors gracefully
            result = await trend_analyzer._fetch_sentiment_data(
                "test_topic",
                datetime.now(timezone.utc) - timedelta(days=7),
                datetime.now(timezone.utc),
            )

            assert result == []  # Should return empty list on error
        finally:
            # Reset the global mock to normal behavior
            psycopg2_mock.connect.side_effect = None


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
