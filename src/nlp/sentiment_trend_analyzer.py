"""
Historical Sentiment Trend Analysis System

This module implements comprehensive sentiment trend analysis for news articles,
providing capabilities for tracking sentiment changes over time, generating alerts
for significant shifts, and storing trend data for visualization.

Addresses Issue #34 requirements:
1. Analyze historical sentiment trends per topic
2. Generate sentiment change alerts when shifts occur
3. Store trend data in Redshift for visualization
"""

import asyncio
import json
import logging
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import Json, execute_batch
from scipy import stats
from sklearn.preprocessing import MinMaxScaler

from src.nlp.keyword_topic_extractor import KeywordTopicExtractor
from src.nlp.sentiment_analysis import SentimentAnalyzer

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class SentimentTrendPoint:
    """Represents a single point in sentiment trend data."""

    date: datetime
    topic: str
    sentiment_score: float
    sentiment_label: str
    confidence: float
    article_count: int
    source_articles: List[str]
    metadata: Dict[str, Any]


@dataclass
class TrendAlert:
    """Represents a sentiment trend alert."""

    alert_id: str
    topic: str
    alert_type: str  # 'significant_shift', 'trend_reversal', 'volatility_spike'
    severity: str  # 'low', 'medium', 'high', 'critical'
    current_sentiment: float
    previous_sentiment: float
    change_magnitude: float
    change_percentage: float
    confidence: float
    time_window: str
    triggered_at: datetime
    description: str
    affected_articles: List[str]
    metadata: Dict[str, Any]


@dataclass
class TopicTrendSummary:
    """Summary of sentiment trends for a specific topic."""

    topic: str
    time_range: Tuple[datetime, datetime]
    current_sentiment: float
    average_sentiment: float
    sentiment_volatility: float
    trend_direction: str  # 'increasing', 'decreasing', 'stable'
    trend_strength: float
    significant_changes: List[TrendAlert]
    data_points: List[SentimentTrendPoint]
    statistical_summary: Dict[str, Any]


class SentimentTrendAnalyzer:
    """
    Analyzes historical sentiment trends for news topics and generates alerts
    for significant changes in sentiment patterns.
    """

    def __init__(
        self,
        redshift_host: str,
        redshift_port: int,
        redshift_database: str,
        redshift_user: str,
        redshift_password: str,
        sentiment_analyzer: Optional[SentimentAnalyzer] = None,
        topic_extractor: Optional[KeywordTopicExtractor] = None,
    ):
        """
        Initialize the sentiment trend analyzer.

        Args:
            redshift_host: Redshift cluster host
            redshift_port: Redshift port
            redshift_database: Database name
            redshift_user: Database user
            redshift_password: Database password
            sentiment_analyzer: Optional sentiment analyzer instance
            topic_extractor: Optional topic extraction instance
        """
        self.conn_params = {
            "host": redshift_host,
            "port": redshift_port,
            "database": redshift_database,
            "user": redshift_user,
            "password": redshift_password,
        }

        self.sentiment_analyzer = sentiment_analyzer or SentimentAnalyzer()
        self.topic_extractor = topic_extractor or KeywordTopicExtractor()

        # Trend analysis configuration
        self.config = {
            "trend_window_days": 30,
            "alert_thresholds": {
                "significant_shift": 0.3,  # Minimum change to trigger alert
                "trend_reversal": 0.2,  # Threshold for trend reversal detection
                "volatility_spike": 0.4,  # Threshold for volatility alerts
            },
            "min_articles_for_trend": 5,  # Minimum articles needed for trend analysis
            "smoothing_window": 7,  # Days for moving average smoothing
            "topics_of_interest": [
                "politics",
                "technology",
                "economy",
                "healthcare",
                "climate",
                "education",
                "security",
                "international",
            ],
        }

        logger.info("SentimentTrendAnalyzer initialized")
        self._initialize_database_schema()

    def _initialize_database_schema(self):
        """Initialize database tables for sentiment trend analysis."""
        try:
            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor() as cursor:
                    # Create sentiment trends table
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS sentiment_trends (
                            id SERIAL PRIMARY KEY,
                            topic VARCHAR(255) NOT NULL,
                            date DATE NOT NULL,
                            sentiment_score FLOAT NOT NULL,
                            sentiment_label VARCHAR(50) NOT NULL,
                            confidence FLOAT NOT NULL,
                            article_count INTEGER NOT NULL,
                            source_articles TEXT[], -- Array of article IDs
                            trend_metadata JSONB,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE(topic, date)
                        );
                    """
                    )

                    # Create sentiment alerts table
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS sentiment_alerts (
                            id SERIAL PRIMARY KEY,
                            alert_id VARCHAR(255) UNIQUE NOT NULL,
                            topic VARCHAR(255) NOT NULL,
                            alert_type VARCHAR(100) NOT NULL,
                            severity VARCHAR(50) NOT NULL,
                            current_sentiment FLOAT NOT NULL,
                            previous_sentiment FLOAT NOT NULL,
                            change_magnitude FLOAT NOT NULL,
                            change_percentage FLOAT NOT NULL,
                            confidence FLOAT NOT NULL,
                            time_window VARCHAR(50) NOT NULL,
                            triggered_at TIMESTAMP NOT NULL,
                            description TEXT,
                            affected_articles TEXT[], -- Array of article IDs
                            alert_metadata JSONB,
                            resolved_at TIMESTAMP,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """
                    )

                    # Create topic sentiment summary table for quick access
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS topic_sentiment_summary (
                            id SERIAL PRIMARY KEY,
                            topic VARCHAR(255) UNIQUE NOT NULL,
                            current_sentiment FLOAT,
                            average_sentiment FLOAT,
                            sentiment_volatility FLOAT,
                            trend_direction VARCHAR(50),
                            trend_strength FLOAT,
                            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            data_points_count INTEGER DEFAULT 0,
                            summary_metadata JSONB
                        );
                    """
                    )

                    # Create indexes for better query performance
                    cursor.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_sentiment_trends_topic_date 
                        ON sentiment_trends(topic, date DESC);
                    """
                    )

                    cursor.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_sentiment_alerts_topic_triggered 
                        ON sentiment_alerts(topic, triggered_at DESC);
                    """
                    )

                    conn.commit()
                    logger.info("Database schema initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize database schema: {str(e)}")
            raise

    async def analyze_historical_trends(
        self,
        topic: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        time_granularity: str = "daily",
    ) -> List[TopicTrendSummary]:
        """
        Analyze historical sentiment trends for specified topics and time period.

        Args:
            topic: Specific topic to analyze (None for all topics)
            start_date: Start date for analysis (default: 30 days ago)
            end_date: End date for analysis (default: today)
            time_granularity: 'daily', 'weekly', or 'monthly'

        Returns:
            List of topic trend summaries
        """
        try:
            logger.info(
                f"Analyzing historical sentiment trends for topic: {topic or 'all'}"
            )

            # Set default date range if not provided
            if not end_date:
                end_date = datetime.now(timezone.utc)
            if not start_date:
                start_date = end_date - timedelta(days=self.config["trend_window_days"])

            # Get sentiment data from database
            sentiment_data = await self._fetch_sentiment_data(
                topic, start_date, end_date
            )

            if not sentiment_data:
                logger.warning("No sentiment data found for the specified criteria")
                return []

            # Process data by topic
            topics_data = self._group_data_by_topic(sentiment_data)
            trend_summaries = []

            for topic_name, topic_data in topics_data.items():
                if len(topic_data) < self.config["min_articles_for_trend"]:
                    logger.warning(
                        f"Insufficient data for topic {topic_name}: {len(topic_data)} articles"
                    )
                    continue

                # Aggregate data by time granularity
                aggregated_data = self._aggregate_by_time_granularity(
                    topic_data, time_granularity
                )

                # Create trend points
                trend_points = self._create_trend_points(topic_name, aggregated_data)

                # Calculate trend statistics
                trend_summary = self._calculate_trend_summary(
                    topic_name, trend_points, (start_date, end_date)
                )

                # Store trend data in database
                await self._store_trend_data(trend_points)

                trend_summaries.append(trend_summary)

            logger.info(f"Completed trend analysis for {len(trend_summaries)} topics")
            return trend_summaries

        except Exception as e:
            logger.error(f"Error in analyze_historical_trends: {str(e)}")
            raise

    async def generate_sentiment_alerts(
        self, topic: Optional[str] = None, lookback_days: int = 7
    ) -> List[TrendAlert]:
        """
        Generate alerts for significant sentiment changes.

        Args:
            topic: Specific topic to check (None for all topics)
            lookback_days: Days to look back for change detection

        Returns:
            List of trend alerts
        """
        try:
            logger.info(f"Generating sentiment alerts for topic: {topic or 'all'}")

            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(
                days=lookback_days * 2
            )  # Get more data for comparison

            # Get recent sentiment data
            sentiment_data = await self._fetch_sentiment_data(
                topic, start_date, end_date
            )

            if not sentiment_data:
                return []

            # Group by topic and analyze for alerts
            topics_data = self._group_data_by_topic(sentiment_data)
            alerts = []

            for topic_name, topic_data in topics_data.items():
                if len(topic_data) < self.config["min_articles_for_trend"]:
                    continue

                # Analyze topic for alerts
                topic_alerts = await self._detect_sentiment_alerts(
                    topic_name, topic_data, lookback_days
                )
                alerts.extend(topic_alerts)

            # Store alerts in database
            if alerts:
                await self._store_alerts(alerts)

            logger.info(f"Generated {len(alerts)} sentiment alerts")
            return alerts

        except Exception as e:
            logger.error(f"Error generating sentiment alerts: {str(e)}")
            raise

    async def _fetch_sentiment_data(
        self, topic: Optional[str], start_date: datetime, end_date: datetime
    ) -> List[Dict[str, Any]]:
        """Fetch sentiment data from database."""
        try:
            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor() as cursor:
                    if topic:
                        # Query for specific topic
                        cursor.execute(
                            """
                            SELECT 
                                na.id,
                                na.title,
                                na.content,
                                na.publish_date,
                                na.sentiment_label,
                                na.sentiment_score,
                                na.sentiment_confidence,
                                kt.topic,
                                kt.keywords
                            FROM news_articles na
                            JOIN keyword_topics kt ON na.id = kt.article_id
                            WHERE kt.topic = %s
                            AND na.publish_date BETWEEN %s AND %s
                            AND na.sentiment_score IS NOT NULL
                            ORDER BY na.publish_date DESC
                        """,
                            (topic, start_date.date(), end_date.date()),
                        )
                    else:
                        # Query for all topics
                        cursor.execute(
                            """
                            SELECT 
                                na.id,
                                na.title,
                                na.content,
                                na.publish_date,
                                na.sentiment_label,
                                na.sentiment_score,
                                na.sentiment_confidence,
                                kt.topic,
                                kt.keywords
                            FROM news_articles na
                            JOIN keyword_topics kt ON na.id = kt.article_id
                            WHERE na.publish_date BETWEEN %s AND %s
                            AND na.sentiment_score IS NOT NULL
                            ORDER BY na.publish_date DESC, kt.topic
                        """,
                            (start_date.date(), end_date.date()),
                        )

                    results = cursor.fetchall()

                    # Convert to dictionaries
                    columns = [desc[0] for desc in cursor.description]
                    return [dict(zip(columns, row)) for row in results]

        except Exception as e:
            logger.error(f"Error fetching sentiment data: {str(e)}")
            return []

    def _group_data_by_topic(
        self, sentiment_data: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Group sentiment data by topic."""
        topics_data = defaultdict(list)

        for item in sentiment_data:
            topic = item.get("topic", "unknown")
            topics_data[topic].append(item)

        return dict(topics_data)

    def _aggregate_by_time_granularity(
        self, topic_data: List[Dict[str, Any]], granularity: str
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Aggregate data by specified time granularity."""
        aggregated = defaultdict(list)

        for item in topic_data:
            publish_date = item["publish_date"]

            if granularity == "daily":
                key = publish_date.strftime("%Y-%m-%d")
            elif granularity == "weekly":
                # Use Monday as the start of the week
                week_start = publish_date - timedelta(days=publish_date.weekday())
                key = week_start.strftime("%Y-%m-%d")
            elif granularity == "monthly":
                key = publish_date.strftime("%Y-%m")
            else:
                key = publish_date.strftime("%Y-%m-%d")  # Default to daily

            aggregated[key].append(item)

        return dict(aggregated)

    def _create_trend_points(
        self, topic: str, aggregated_data: Dict[str, List[Dict[str, Any]]]
    ) -> List[SentimentTrendPoint]:
        """Create sentiment trend points from aggregated data."""
        trend_points = []

        for date_key, articles in aggregated_data.items():
            if not articles:
                continue

            # Calculate average sentiment for this time period
            sentiment_scores = [article["sentiment_score"] for article in articles]
            confidences = [article["sentiment_confidence"] for article in articles]

            avg_sentiment = statistics.mean(sentiment_scores)
            avg_confidence = statistics.mean(confidences)

            # Determine sentiment label based on average score
            if avg_sentiment >= 0.1:
                sentiment_label = "positive"
            elif avg_sentiment <= -0.1:
                sentiment_label = "negative"
            else:
                sentiment_label = "neutral"

            # Parse date
            try:
                if len(date_key) == 7:  # Monthly format YYYY-MM
                    date = datetime.strptime(date_key + "-01", "%Y-%m-%d")
                else:  # Daily/weekly format YYYY-MM-DD
                    date = datetime.strptime(date_key, "%Y-%m-%d")
            except ValueError:
                logger.warning(f"Failed to parse date: {date_key}")
                continue

            trend_point = SentimentTrendPoint(
                date=date,
                topic=topic,
                sentiment_score=avg_sentiment,
                sentiment_label=sentiment_label,
                confidence=avg_confidence,
                article_count=len(articles),
                source_articles=[article["id"] for article in articles],
                metadata={
                    "sentiment_distribution": {
                        "min": min(sentiment_scores),
                        "max": max(sentiment_scores),
                        "std": (
                            statistics.stdev(sentiment_scores)
                            if len(sentiment_scores) > 1
                            else 0
                        ),
                    },
                    "date_key": date_key,
                },
            )

            trend_points.append(trend_point)

        # Sort by date
        trend_points.sort(key=lambda x: x.date)
        return trend_points

    def _calculate_trend_summary(
        self,
        topic: str,
        trend_points: List[SentimentTrendPoint],
        time_range: Tuple[datetime, datetime],
    ) -> TopicTrendSummary:
        """Calculate comprehensive trend summary for a topic."""
        if not trend_points:
            return TopicTrendSummary(
                topic=topic,
                time_range=time_range,
                current_sentiment=0.0,
                average_sentiment=0.0,
                sentiment_volatility=0.0,
                trend_direction="stable",
                trend_strength=0.0,
                significant_changes=[],
                data_points=[],
                statistical_summary={},
            )

        sentiment_scores = [point.sentiment_score for point in trend_points]

        # Calculate basic statistics
        current_sentiment = trend_points[-1].sentiment_score
        average_sentiment = statistics.mean(sentiment_scores)
        sentiment_volatility = (
            statistics.stdev(sentiment_scores) if len(sentiment_scores) > 1 else 0.0
        )

        # Calculate trend direction and strength using linear regression
        if len(trend_points) >= 2:
            x_values = list(range(len(trend_points)))
            slope, intercept, r_value, p_value, std_err = stats.linregress(
                x_values, sentiment_scores
            )

            trend_strength = abs(r_value)  # Correlation coefficient as trend strength

            if slope > 0.01:
                trend_direction = "increasing"
            elif slope < -0.01:
                trend_direction = "decreasing"
            else:
                trend_direction = "stable"
        else:
            slope = 0
            trend_direction = "stable"
            trend_strength = 0.0
            r_value = 0
            p_value = 1

        # Statistical summary
        statistical_summary = {
            "min_sentiment": min(sentiment_scores),
            "max_sentiment": max(sentiment_scores),
            "median_sentiment": statistics.median(sentiment_scores),
            "trend_slope": slope,
            "correlation_coefficient": r_value,
            "p_value": p_value,
            "total_articles": sum(point.article_count for point in trend_points),
        }

        return TopicTrendSummary(
            topic=topic,
            time_range=time_range,
            current_sentiment=current_sentiment,
            average_sentiment=average_sentiment,
            sentiment_volatility=sentiment_volatility,
            trend_direction=trend_direction,
            trend_strength=trend_strength,
            significant_changes=[],  # Will be populated by alert detection
            data_points=trend_points,
            statistical_summary=statistical_summary,
        )

    async def _detect_sentiment_alerts(
        self, topic: str, topic_data: List[Dict[str, Any]], lookback_days: int
    ) -> List[TrendAlert]:
        """Detect sentiment alerts for a specific topic."""
        alerts = []

        try:
            # Sort data by date
            topic_data.sort(key=lambda x: x["publish_date"])

            # Split data into current and previous periods
            cutoff_date = datetime.now(timezone.utc).date() - timedelta(
                days=lookback_days
            )

            current_period = [
                item for item in topic_data if item["publish_date"] >= cutoff_date
            ]
            previous_period = [
                item for item in topic_data if item["publish_date"] < cutoff_date
            ]

            if not current_period or not previous_period:
                return alerts

            # Calculate sentiment averages for both periods
            current_sentiment = statistics.mean(
                [item["sentiment_score"] for item in current_period]
            )
            previous_sentiment = statistics.mean(
                [item["sentiment_score"] for item in previous_period]
            )

            change_magnitude = abs(current_sentiment - previous_sentiment)
            change_percentage = (
                change_magnitude / (abs(previous_sentiment) + 0.001)
            ) * 100

            # Check for significant shift
            if change_magnitude >= self.config["alert_thresholds"]["significant_shift"]:
                alert = self._create_alert(
                    topic=topic,
                    alert_type="significant_shift",
                    current_sentiment=current_sentiment,
                    previous_sentiment=previous_sentiment,
                    change_magnitude=change_magnitude,
                    change_percentage=change_percentage,
                    time_window=f"{lookback_days}d",
                    affected_articles=[item["id"] for item in current_period],
                )
                alerts.append(alert)

            # Check for trend reversal
            if (previous_sentiment > 0.1 and current_sentiment < -0.1) or (
                previous_sentiment < -0.1 and current_sentiment > 0.1
            ):
                if (
                    change_magnitude
                    >= self.config["alert_thresholds"]["trend_reversal"]
                ):
                    alert = self._create_alert(
                        topic=topic,
                        alert_type="trend_reversal",
                        current_sentiment=current_sentiment,
                        previous_sentiment=previous_sentiment,
                        change_magnitude=change_magnitude,
                        change_percentage=change_percentage,
                        time_window=f"{lookback_days}d",
                        affected_articles=[item["id"] for item in current_period],
                    )
                    alerts.append(alert)

            # Check for volatility spike
            current_volatility = (
                statistics.stdev([item["sentiment_score"] for item in current_period])
                if len(current_period) > 1
                else 0
            )
            previous_volatility = (
                statistics.stdev([item["sentiment_score"] for item in previous_period])
                if len(previous_period) > 1
                else 0
            )

            volatility_increase = current_volatility - previous_volatility
            if (
                volatility_increase
                >= self.config["alert_thresholds"]["volatility_spike"]
            ):
                alert = self._create_alert(
                    topic=topic,
                    alert_type="volatility_spike",
                    current_sentiment=current_sentiment,
                    previous_sentiment=previous_sentiment,
                    change_magnitude=volatility_increase,
                    change_percentage=(
                        volatility_increase / (previous_volatility + 0.001)
                    )
                    * 100,
                    time_window=f"{lookback_days}d",
                    affected_articles=[item["id"] for item in current_period],
                )
                alerts.append(alert)

        except Exception as e:
            logger.error(f"Error detecting alerts for topic {topic}: {str(e)}")

        return alerts

    def _create_alert(
        self,
        topic: str,
        alert_type: str,
        current_sentiment: float,
        previous_sentiment: float,
        change_magnitude: float,
        change_percentage: float,
        time_window: str,
        affected_articles: List[str],
    ) -> TrendAlert:
        """Create a trend alert object."""

        # Determine severity based on magnitude and type
        if change_magnitude >= 0.6:
            severity = "critical"
        elif change_magnitude >= 0.4:
            severity = "high"
        elif change_magnitude >= 0.2:
            severity = "medium"
        else:
            severity = "low"

        # Generate alert ID
        timestamp = datetime.now(timezone.utc)
        alert_id = f"{topic}_{alert_type}_{timestamp.strftime('%Y%m%d_%H%M%S')}"

        # Create description
        direction = "improved" if current_sentiment > previous_sentiment else "declined"
        description = (
            f"Sentiment for '{topic}' has {direction} by {change_percentage:.1f}% "
            f"({previous_sentiment:.3f} → {current_sentiment:.3f}) over {time_window}"
        )

        # Calculate confidence based on change magnitude and affected articles
        confidence = min(
            0.95, max(0.3, change_magnitude + (len(affected_articles) / 100))
        )

        return TrendAlert(
            alert_id=alert_id,
            topic=topic,
            alert_type=alert_type,
            severity=severity,
            current_sentiment=current_sentiment,
            previous_sentiment=previous_sentiment,
            change_magnitude=change_magnitude,
            change_percentage=change_percentage,
            confidence=confidence,
            time_window=time_window,
            triggered_at=timestamp,
            description=description,
            affected_articles=affected_articles,
            metadata={
                "article_count": len(affected_articles),
                "alert_generated_by": "SentimentTrendAnalyzer",
                "analysis_window": time_window,
            },
        )

    async def _store_trend_data(self, trend_points: List[SentimentTrendPoint]):
        """Store trend data in Redshift."""
        if not trend_points:
            return

        try:
            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor() as cursor:
                    # Prepare data for insertion
                    trend_data = []
                    for point in trend_points:
                        trend_data.append(
                            (
                                point.topic,
                                point.date.date(),
                                point.sentiment_score,
                                point.sentiment_label,
                                point.confidence,
                                point.article_count,
                                point.source_articles,
                                Json(point.metadata),
                            )
                        )

                    # Use ON CONFLICT to handle duplicates
                    execute_batch(
                        cursor,
                        """
                        INSERT INTO sentiment_trends 
                        (topic, date, sentiment_score, sentiment_label, confidence, 
                         article_count, source_articles, trend_metadata)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (topic, date) 
                        DO UPDATE SET
                            sentiment_score = EXCLUDED.sentiment_score,
                            sentiment_label = EXCLUDED.sentiment_label,
                            confidence = EXCLUDED.confidence,
                            article_count = EXCLUDED.article_count,
                            source_articles = EXCLUDED.source_articles,
                            trend_metadata = EXCLUDED.trend_metadata
                        """,
                        trend_data,
                    )

                    conn.commit()
                    logger.info(f"Stored {len(trend_data)} trend data points")

        except Exception as e:
            logger.error(f"Error storing trend data: {str(e)}")
            raise

    async def _store_alerts(self, alerts: List[TrendAlert]):
        """Store alerts in Redshift."""
        if not alerts:
            return

        try:
            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor() as cursor:
                    # Prepare data for insertion
                    alert_data = []
                    for alert in alerts:
                        alert_data.append(
                            (
                                alert.alert_id,
                                alert.topic,
                                alert.alert_type,
                                alert.severity,
                                alert.current_sentiment,
                                alert.previous_sentiment,
                                alert.change_magnitude,
                                alert.change_percentage,
                                alert.confidence,
                                alert.time_window,
                                alert.triggered_at,
                                alert.description,
                                alert.affected_articles,
                                Json(alert.metadata),
                            )
                        )

                    # Insert alerts
                    execute_batch(
                        cursor,
                        """
                        INSERT INTO sentiment_alerts 
                        (alert_id, topic, alert_type, severity, current_sentiment,
                         previous_sentiment, change_magnitude, change_percentage, confidence,
                         time_window, triggered_at, description, affected_articles, alert_metadata)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (alert_id) DO NOTHING
                        """,
                        alert_data,
                    )

                    conn.commit()
                    logger.info(f"Stored {len(alert_data)} sentiment alerts")

        except Exception as e:
            logger.error(f"Error storing alerts: {str(e)}")
            raise

    async def get_topic_trend_summary(
        self, topic: str, days: int = 30
    ) -> Optional[TopicTrendSummary]:
        """Get comprehensive trend summary for a specific topic."""
        try:
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=days)

            # Analyze trends for the specific topic
            summaries = await self.analyze_historical_trends(
                topic=topic, start_date=start_date, end_date=end_date
            )

            return summaries[0] if summaries else None

        except Exception as e:
            logger.error(f"Error getting topic trend summary for {topic}: {str(e)}")
            return None

    async def get_active_alerts(
        self,
        topic: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 50,
    ) -> List[TrendAlert]:
        """Get active sentiment alerts."""
        try:
            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor() as cursor:
                    # Build query with optional filters
                    conditions = ["resolved_at IS NULL"]
                    params = []

                    if topic:
                        conditions.append("topic = %s")
                        params.append(topic)

                    if severity:
                        conditions.append("severity = %s")
                        params.append(severity)

                    params.append(limit)

                    query = f"""
                        SELECT alert_id, topic, alert_type, severity, current_sentiment,
                               previous_sentiment, change_magnitude, change_percentage, confidence,
                               time_window, triggered_at, description, affected_articles, alert_metadata
                        FROM sentiment_alerts
                        WHERE {" AND ".join(conditions)}
                        ORDER BY triggered_at DESC
                        LIMIT %s
                    """

                    cursor.execute(query, params)
                    results = cursor.fetchall()

                    # Convert to TrendAlert objects
                    alerts = []
                    for row in results:
                        alert = TrendAlert(
                            alert_id=row[0],
                            topic=row[1],
                            alert_type=row[2],
                            severity=row[3],
                            current_sentiment=row[4],
                            previous_sentiment=row[5],
                            change_magnitude=row[6],
                            change_percentage=row[7],
                            confidence=row[8],
                            time_window=row[9],
                            triggered_at=row[10],
                            description=row[11],
                            affected_articles=row[12] or [],
                            metadata=row[13] or {},
                        )
                        alerts.append(alert)

                    return alerts

        except Exception as e:
            logger.error(f"Error getting active alerts: {str(e)}")
            return []

    async def update_topic_summaries(self):
        """Update topic sentiment summaries for quick access."""
        try:
            # Get all topics
            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT DISTINCT topic FROM sentiment_trends
                        WHERE date >= %s
                    """,
                        (datetime.now().date() - timedelta(days=30),),
                    )

                    topics = [row[0] for row in cursor.fetchall()]

            # Update summary for each topic
            for topic in topics:
                try:
                    summary = await self.get_topic_trend_summary(topic)
                    if summary:
                        await self._store_topic_summary(summary)
                except Exception as e:
                    logger.error(f"Error updating summary for topic {topic}: {str(e)}")

            logger.info(f"Updated summaries for {len(topics)} topics")

        except Exception as e:
            logger.error(f"Error updating topic summaries: {str(e)}")

    async def _store_topic_summary(self, summary: TopicTrendSummary):
        """Store topic summary in database."""
        try:
            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO topic_sentiment_summary 
                        (topic, current_sentiment, average_sentiment, sentiment_volatility,
                         trend_direction, trend_strength, data_points_count, summary_metadata)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (topic) 
                        DO UPDATE SET
                            current_sentiment = EXCLUDED.current_sentiment,
                            average_sentiment = EXCLUDED.average_sentiment,
                            sentiment_volatility = EXCLUDED.sentiment_volatility,
                            trend_direction = EXCLUDED.trend_direction,
                            trend_strength = EXCLUDED.trend_strength,
                            data_points_count = EXCLUDED.data_points_count,
                            summary_metadata = EXCLUDED.summary_metadata,
                            last_updated = CURRENT_TIMESTAMP
                    """,
                        (
                            summary.topic,
                            summary.current_sentiment,
                            summary.average_sentiment,
                            summary.sentiment_volatility,
                            summary.trend_direction,
                            summary.trend_strength,
                            len(summary.data_points),
                            Json(summary.statistical_summary),
                        ),
                    )

                    conn.commit()

        except Exception as e:
            logger.error(f"Error storing topic summary: {str(e)}")


# Utility functions for integration with other systems
async def analyze_sentiment_trends_for_topic(
    topic: str, redshift_config: Dict[str, Any], days: int = 30
) -> Optional[TopicTrendSummary]:
    """
    Convenience function to analyze sentiment trends for a specific topic.

    Args:
        topic: Topic to analyze
        redshift_config: Redshift connection configuration
        days: Number of days to analyze

    Returns:
        Topic trend summary or None
    """
    analyzer = SentimentTrendAnalyzer(**redshift_config)
    return await analyzer.get_topic_trend_summary(topic, days)


async def generate_daily_sentiment_alerts(
    redshift_config: Dict[str, Any],
) -> List[TrendAlert]:
    """
    Convenience function to generate daily sentiment alerts.

    Args:
        redshift_config: Redshift connection configuration

    Returns:
        List of generated alerts
    """
    analyzer = SentimentTrendAnalyzer(**redshift_config)
    return await analyzer.generate_sentiment_alerts(lookback_days=7)
