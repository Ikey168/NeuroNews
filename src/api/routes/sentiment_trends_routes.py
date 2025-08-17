"""
API Routes for Historical Sentiment Trend Analysis

This module provides FastAPI endpoints for accessing sentiment trend data,
alerts, and analysis results from the sentiment trend analyzer.
"""

from fastapi import APIRouter, HTTPException, Query, Depends, BackgroundTasks
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime, timedelta
from pydantic import BaseModel, Field

from src.nlp.sentiment_trend_analyzer import (
    SentimentTrendAnalyzer, 
    TopicTrendSummary, 
    TrendAlert,
    analyze_sentiment_trends_for_topic,
    generate_daily_sentiment_alerts
)
from src.core.config import get_settings

# Set up logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1", tags=["sentiment-trends"])

# Get configuration
settings = get_settings()


# Pydantic models for request/response
class TrendAnalysisRequest(BaseModel):
    """Request model for trend analysis."""
    topic: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    time_granularity: str = Field(default="daily", regex="^(daily|weekly|monthly)$")


class AlertGenerationRequest(BaseModel):
    """Request model for alert generation."""
    topic: Optional[str] = None
    lookback_days: int = Field(default=7, ge=1, le=30)


class TrendPointResponse(BaseModel):
    """Response model for trend points."""
    date: datetime
    topic: str
    sentiment_score: float
    sentiment_label: str
    confidence: float
    article_count: int


class TrendSummaryResponse(BaseModel):
    """Response model for trend summary."""
    topic: str
    time_range: Dict[str, datetime]
    current_sentiment: float
    average_sentiment: float
    sentiment_volatility: float
    trend_direction: str
    trend_strength: float
    data_points_count: int
    statistical_summary: Dict[str, Any]


class AlertResponse(BaseModel):
    """Response model for alerts."""
    alert_id: str
    topic: str
    alert_type: str
    severity: str
    current_sentiment: float
    previous_sentiment: float
    change_magnitude: float
    change_percentage: float
    confidence: float
    time_window: str
    triggered_at: datetime
    description: str
    affected_articles_count: int


async def get_sentiment_analyzer() -> SentimentTrendAnalyzer:
    """Dependency to get SentimentTrendAnalyzer instance."""
    redshift_config = {
        'redshift_host': settings.REDSHIFT_HOST,
        'redshift_port': settings.REDSHIFT_PORT,
        'redshift_database': settings.REDSHIFT_DATABASE,
        'redshift_user': settings.REDSHIFT_USER,
        'redshift_password': settings.REDSHIFT_PASSWORD
    }
    return SentimentTrendAnalyzer(**redshift_config)


@router.get("/sentiment_trends/analyze")
async def analyze_sentiment_trends(
    topic: Optional[str] = Query(None, description="Specific topic to analyze"),
    start_date: Optional[datetime] = Query(None, description="Start date for analysis"),
    end_date: Optional[datetime] = Query(None, description="End date for analysis"),
    time_granularity: str = Query("daily", regex="^(daily|weekly|monthly)$", description="Time granularity"),
    analyzer: SentimentTrendAnalyzer = Depends(get_sentiment_analyzer)
) -> Dict[str, Any]:
    """
    Analyze historical sentiment trends for specified topics and time period.
    
    This endpoint analyzes sentiment trends over time, providing insights into
    how sentiment has changed for specific topics or across all topics.
    
    Args:
        topic: Specific topic to analyze (None for all topics)
        start_date: Start date for analysis (default: 30 days ago)
        end_date: End date for analysis (default: today)
        time_granularity: Time granularity ('daily', 'weekly', 'monthly')
        
    Returns:
        Dictionary containing trend summaries and analysis results
    """
    try:
        logger.info(f"API request for sentiment trend analysis: topic={topic}, granularity={time_granularity}")
        
        # Validate date range
        if start_date and end_date and start_date >= end_date:
            raise HTTPException(
                status_code=400,
                detail="Start date must be before end date"
            )
        
        # Set reasonable defaults
        if not end_date:
            end_date = datetime.now()
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        # Limit analysis to reasonable time ranges
        max_days = 365
        if (end_date - start_date).days > max_days:
            raise HTTPException(
                status_code=400,
                detail=f"Date range too large. Maximum {max_days} days allowed."
            )
        
        # Perform trend analysis
        trend_summaries = await analyzer.analyze_historical_trends(
            topic=topic,
            start_date=start_date,
            end_date=end_date,
            time_granularity=time_granularity
        )
        
        # Format response
        response_summaries = []
        for summary in trend_summaries:
            summary_response = TrendSummaryResponse(
                topic=summary.topic,
                time_range={
                    "start": summary.time_range[0],
                    "end": summary.time_range[1]
                },
                current_sentiment=summary.current_sentiment,
                average_sentiment=summary.average_sentiment,
                sentiment_volatility=summary.sentiment_volatility,
                trend_direction=summary.trend_direction,
                trend_strength=summary.trend_strength,
                data_points_count=len(summary.data_points),
                statistical_summary=summary.statistical_summary
            )
            response_summaries.append(summary_response)
        
        # Prepare trend points for visualization
        all_trend_points = []
        for summary in trend_summaries:
            for point in summary.data_points:
                trend_point = TrendPointResponse(
                    date=point.date,
                    topic=point.topic,
                    sentiment_score=point.sentiment_score,
                    sentiment_label=point.sentiment_label,
                    confidence=point.confidence,
                    article_count=point.article_count
                )
                all_trend_points.append(trend_point)
        
        response = {
            'analysis_parameters': {
                'topic': topic,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'time_granularity': time_granularity
            },
            'summary_count': len(response_summaries),
            'trend_summaries': response_summaries,
            'trend_points': all_trend_points,
            'timestamp': datetime.now().isoformat(),
            'status': 'success'
        }
        
        logger.info(f"Successfully analyzed trends for {len(response_summaries)} topics")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing sentiment trends: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyze sentiment trends: {str(e)}"
        )


@router.post("/sentiment_trends/alerts/generate")
async def generate_sentiment_alerts(
    background_tasks: BackgroundTasks,
    topic: Optional[str] = Query(None, description="Specific topic to check for alerts"),
    lookback_days: int = Query(7, ge=1, le=30, description="Days to look back for change detection"),
    analyzer: SentimentTrendAnalyzer = Depends(get_sentiment_analyzer)
) -> Dict[str, Any]:
    """
    Generate alerts for significant sentiment changes.
    
    This endpoint analyzes recent sentiment data and generates alerts for
    significant changes, trend reversals, and volatility spikes.
    
    Args:
        topic: Specific topic to check (None for all topics)
        lookback_days: Days to look back for change detection (1-30)
        
    Returns:
        Dictionary containing generated alerts and analysis metadata
    """
    try:
        logger.info(f"API request to generate sentiment alerts: topic={topic}, lookback_days={lookback_days}")
        
        # Generate alerts
        alerts = await analyzer.generate_sentiment_alerts(
            topic=topic,
            lookback_days=lookback_days
        )
        
        # Format alerts for response
        alert_responses = []
        for alert in alerts:
            alert_response = AlertResponse(
                alert_id=alert.alert_id,
                topic=alert.topic,
                alert_type=alert.alert_type,
                severity=alert.severity,
                current_sentiment=alert.current_sentiment,
                previous_sentiment=alert.previous_sentiment,
                change_magnitude=alert.change_magnitude,
                change_percentage=alert.change_percentage,
                confidence=alert.confidence,
                time_window=alert.time_window,
                triggered_at=alert.triggered_at,
                description=alert.description,
                affected_articles_count=len(alert.affected_articles)
            )
            alert_responses.append(alert_response)
        
        # Schedule background task to update topic summaries
        background_tasks.add_task(analyzer.update_topic_summaries)
        
        response = {
            'generation_parameters': {
                'topic': topic,
                'lookback_days': lookback_days
            },
            'alerts_generated': len(alert_responses),
            'alerts': alert_responses,
            'severity_breakdown': {
                'critical': len([a for a in alerts if a.severity == 'critical']),
                'high': len([a for a in alerts if a.severity == 'high']),
                'medium': len([a for a in alerts if a.severity == 'medium']),
                'low': len([a for a in alerts if a.severity == 'low'])
            },
            'timestamp': datetime.now().isoformat(),
            'status': 'success'
        }
        
        logger.info(f"Generated {len(alerts)} sentiment alerts")
        return response
        
    except Exception as e:
        logger.error(f"Error generating sentiment alerts: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate sentiment alerts: {str(e)}"
        )


@router.get("/sentiment_trends/alerts")
async def get_sentiment_alerts(
    topic: Optional[str] = Query(None, description="Filter alerts by topic"),
    severity: Optional[str] = Query(None, regex="^(low|medium|high|critical)$", description="Filter by severity"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of alerts to return"),
    include_resolved: bool = Query(False, description="Include resolved alerts"),
    analyzer: SentimentTrendAnalyzer = Depends(get_sentiment_analyzer)
) -> Dict[str, Any]:
    """
    Get sentiment trend alerts with optional filtering.
    
    Args:
        topic: Filter alerts by topic
        severity: Filter by severity level
        limit: Maximum number of alerts to return (1-200)
        include_resolved: Whether to include resolved alerts
        
    Returns:
        Dictionary containing filtered alerts and metadata
    """
    try:
        logger.info(f"API request for sentiment alerts: topic={topic}, severity={severity}")
        
        # Get alerts (currently only supports active alerts)
        if include_resolved:
            # TODO: Add support for resolved alerts in the analyzer
            logger.warning("Resolved alerts not yet supported, returning active alerts only")
        
        alerts = await analyzer.get_active_alerts(
            topic=topic,
            severity=severity,
            limit=limit
        )
        
        # Format alerts for response
        alert_responses = []
        for alert in alerts:
            alert_response = AlertResponse(
                alert_id=alert.alert_id,
                topic=alert.topic,
                alert_type=alert.alert_type,
                severity=alert.severity,
                current_sentiment=alert.current_sentiment,
                previous_sentiment=alert.previous_sentiment,
                change_magnitude=alert.change_magnitude,
                change_percentage=alert.change_percentage,
                confidence=alert.confidence,
                time_window=alert.time_window,
                triggered_at=alert.triggered_at,
                description=alert.description,
                affected_articles_count=len(alert.affected_articles)
            )
            alert_responses.append(alert_response)
        
        response = {
            'query_parameters': {
                'topic': topic,
                'severity': severity,
                'limit': limit,
                'include_resolved': include_resolved
            },
            'total_alerts': len(alert_responses),
            'alerts': alert_responses,
            'alert_types': list(set(alert.alert_type for alert in alerts)),
            'topics_with_alerts': list(set(alert.topic for alert in alerts)),
            'timestamp': datetime.now().isoformat(),
            'status': 'success'
        }
        
        logger.info(f"Retrieved {len(alerts)} sentiment alerts")
        return response
        
    except Exception as e:
        logger.error(f"Error retrieving sentiment alerts: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve sentiment alerts: {str(e)}"
        )


@router.get("/sentiment_trends/topic/{topic}")
async def get_topic_sentiment_trends(
    topic: str,
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    analyzer: SentimentTrendAnalyzer = Depends(get_sentiment_analyzer)
) -> Dict[str, Any]:
    """
    Get comprehensive sentiment trend analysis for a specific topic.
    
    Args:
        topic: Topic to analyze
        days: Number of days to analyze (1-365)
        
    Returns:
        Dictionary containing comprehensive topic trend analysis
    """
    try:
        logger.info(f"API request for topic sentiment trends: {topic}, days={days}")
        
        # Validate topic
        if not topic or len(topic.strip()) < 2:
            raise HTTPException(
                status_code=400,
                detail="Topic must be at least 2 characters long"
            )
        
        # Get trend summary
        trend_summary = await analyzer.get_topic_trend_summary(topic, days)
        
        if not trend_summary:
            raise HTTPException(
                status_code=404,
                detail=f"No sentiment data found for topic '{topic}' in the last {days} days"
            )
        
        # Format trend points
        trend_points = []
        for point in trend_summary.data_points:
            trend_point = TrendPointResponse(
                date=point.date,
                topic=point.topic,
                sentiment_score=point.sentiment_score,
                sentiment_label=point.sentiment_label,
                confidence=point.confidence,
                article_count=point.article_count
            )
            trend_points.append(trend_point)
        
        # Get recent alerts for this topic
        recent_alerts = await analyzer.get_active_alerts(topic=topic, limit=10)
        alert_responses = []
        for alert in recent_alerts:
            alert_response = AlertResponse(
                alert_id=alert.alert_id,
                topic=alert.topic,
                alert_type=alert.alert_type,
                severity=alert.severity,
                current_sentiment=alert.current_sentiment,
                previous_sentiment=alert.previous_sentiment,
                change_magnitude=alert.change_magnitude,
                change_percentage=alert.change_percentage,
                confidence=alert.confidence,
                time_window=alert.time_window,
                triggered_at=alert.triggered_at,
                description=alert.description,
                affected_articles_count=len(alert.affected_articles)
            )
            alert_responses.append(alert_response)
        
        response = {
            'topic': topic,
            'analysis_period_days': days,
            'time_range': {
                'start': trend_summary.time_range[0].isoformat(),
                'end': trend_summary.time_range[1].isoformat()
            },
            'sentiment_summary': {
                'current_sentiment': trend_summary.current_sentiment,
                'average_sentiment': trend_summary.average_sentiment,
                'sentiment_volatility': trend_summary.sentiment_volatility,
                'trend_direction': trend_summary.trend_direction,
                'trend_strength': trend_summary.trend_strength
            },
            'statistical_summary': trend_summary.statistical_summary,
            'trend_points': trend_points,
            'recent_alerts': alert_responses,
            'data_quality': {
                'total_data_points': len(trend_points),
                'total_articles_analyzed': trend_summary.statistical_summary.get('total_articles', 0),
                'data_completeness': min(1.0, len(trend_points) / days)
            },
            'timestamp': datetime.now().isoformat(),
            'status': 'success'
        }
        
        logger.info(f"Retrieved sentiment trends for topic '{topic}' with {len(trend_points)} data points")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving topic sentiment trends for {topic}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve sentiment trends for topic: {str(e)}"
        )


@router.get("/sentiment_trends/summary")
async def get_sentiment_trends_summary(
    limit_topics: int = Query(20, ge=1, le=100, description="Maximum number of topics to include"),
    analyzer: SentimentTrendAnalyzer = Depends(get_sentiment_analyzer)
) -> Dict[str, Any]:
    """
    Get an overview summary of sentiment trends across all topics.
    
    Args:
        limit_topics: Maximum number of topics to include in summary
        
    Returns:
        Dictionary containing overall sentiment trends summary
    """
    try:
        logger.info("API request for sentiment trends summary")
        
        # Get recent trend data for all topics
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)  # Last week
        
        trend_summaries = await analyzer.analyze_historical_trends(
            topic=None,
            start_date=start_date,
            end_date=end_date,
            time_granularity='daily'
        )
        
        # Limit and sort topics by relevance/activity
        trend_summaries = sorted(
            trend_summaries,
            key=lambda x: (len(x.data_points), x.statistical_summary.get('total_articles', 0)),
            reverse=True
        )[:limit_topics]
        
        # Get active alerts summary
        all_alerts = await analyzer.get_active_alerts(limit=100)
        
        # Calculate overall statistics
        if trend_summaries:
            overall_sentiment = sum(s.average_sentiment for s in trend_summaries) / len(trend_summaries)
            overall_volatility = sum(s.sentiment_volatility for s in trend_summaries) / len(trend_summaries)
        else:
            overall_sentiment = 0.0
            overall_volatility = 0.0
        
        # Group alerts by severity and type
        alert_breakdown = {
            'by_severity': {'critical': 0, 'high': 0, 'medium': 0, 'low': 0},
            'by_type': {}
        }
        
        for alert in all_alerts:
            alert_breakdown['by_severity'][alert.severity] += 1
            alert_breakdown['by_type'][alert.alert_type] = alert_breakdown['by_type'].get(alert.alert_type, 0) + 1
        
        # Format topic summaries
        topic_summaries = []
        for summary in trend_summaries:
            topic_summary = {
                'topic': summary.topic,
                'current_sentiment': summary.current_sentiment,
                'trend_direction': summary.trend_direction,
                'trend_strength': summary.trend_strength,
                'volatility': summary.sentiment_volatility,
                'data_points': len(summary.data_points),
                'total_articles': summary.statistical_summary.get('total_articles', 0)
            }
            topic_summaries.append(topic_summary)
        
        response = {
            'overall_metrics': {
                'average_sentiment': overall_sentiment,
                'average_volatility': overall_volatility,
                'active_topics': len(trend_summaries),
                'total_alerts': len(all_alerts)
            },
            'topic_summaries': topic_summaries,
            'alert_summary': {
                'total_active_alerts': len(all_alerts),
                'breakdown': alert_breakdown
            },
            'trending_topics': {
                'most_positive': sorted(topic_summaries, key=lambda x: x['current_sentiment'], reverse=True)[:5],
                'most_negative': sorted(topic_summaries, key=lambda x: x['current_sentiment'])[:5],
                'most_volatile': sorted(topic_summaries, key=lambda x: x['volatility'], reverse=True)[:5]
            },
            'analysis_period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'days': 7
            },
            'timestamp': datetime.now().isoformat(),
            'status': 'success'
        }
        
        logger.info(f"Generated sentiment trends summary for {len(topic_summaries)} topics")
        return response
        
    except Exception as e:
        logger.error(f"Error generating sentiment trends summary: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate sentiment trends summary: {str(e)}"
        )


@router.post("/sentiment_trends/update_summaries")
async def update_topic_summaries(
    background_tasks: BackgroundTasks,
    analyzer: SentimentTrendAnalyzer = Depends(get_sentiment_analyzer)
) -> Dict[str, Any]:
    """
    Trigger an update of topic sentiment summaries.
    
    This endpoint triggers a background task to update cached topic summaries
    for faster access to frequently requested data.
    
    Returns:
        Dictionary confirming the update task has been scheduled
    """
    try:
        logger.info("API request to update topic summaries")
        
        # Schedule background task
        background_tasks.add_task(analyzer.update_topic_summaries)
        
        response = {
            'message': 'Topic summaries update scheduled',
            'status': 'scheduled',
            'timestamp': datetime.now().isoformat()
        }
        
        logger.info("Topic summaries update task scheduled")
        return response
        
    except Exception as e:
        logger.error(f"Error scheduling topic summaries update: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to schedule topic summaries update: {str(e)}"
        )


@router.get("/sentiment_trends/health")
async def sentiment_trends_health_check(
    analyzer: SentimentTrendAnalyzer = Depends(get_sentiment_analyzer)
) -> Dict[str, Any]:
    """
    Health check endpoint for sentiment trends service.
    
    Returns:
        Dictionary containing service health information
    """
    try:
        # Test database connection
        test_alerts = await analyzer.get_active_alerts(limit=1)
        
        # Get basic statistics
        with psycopg2.connect(**analyzer.conn_params) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM sentiment_trends")
                trend_count = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM sentiment_alerts WHERE resolved_at IS NULL")
                active_alerts = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(DISTINCT topic) FROM sentiment_trends")
                unique_topics = cursor.fetchone()[0]
        
        response = {
            'service': 'sentiment_trends',
            'status': 'healthy',
            'database_connection': 'ok',
            'statistics': {
                'total_trend_points': trend_count,
                'active_alerts': active_alerts,
                'unique_topics': unique_topics
            },
            'timestamp': datetime.now().isoformat()
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(
            status_code=503,
            detail=f"Service health check failed: {str(e)}"
        )
