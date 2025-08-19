"""
News Veracity API Routes

This module provides API endpoints for fake news detection and trustworthiness scoring.
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.database.redshift_loader import \
    RedshiftETLProcessor as RedshiftConnection
from src.nlp.fake_news_detector import FakeNewsConfig, FakeNewsDetector

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI router
router = APIRouter(prefix="/api/veracity", tags=["veracity"])

# Global detector instance (initialized on first use)
_detector = None


# Pydantic models
class Article(BaseModel):
    article_id: str
    text: str


class BatchVeracityRequest(BaseModel):
    articles: List[Article]


class VeracityResponse(BaseModel):
    article_id: str
    veracity_analysis: Dict[str, Any]
    status: str
    source: str


class BatchVeracityResponse(BaseModel):
    results: List[Dict[str, Any]]
    total_processed: int
    status: str


class StatisticsResponse(BaseModel):
    statistics: Dict[str, Any]
    status: str


class ModelInfoResponse(BaseModel):
    model_info: Dict[str, Any]
    status: str


# Global detector instance (initialized on first use)
_detector = None


def get_detector() -> FakeNewsDetector:
    """Get or initialize the fake news detector."""
    global _detector
    if _detector is None:
        model_name = os.getenv("FAKE_NEWS_MODEL", "roberta-base")
        _detector = FakeNewsDetector(model_name=model_name)
        logger.info(f"Initialized fake news detector with {model_name}")
    return _detector


def store_veracity_result(
    article_id: str,
    result: Dict[str, Any],
    redshift_conn: Optional[RedshiftConnection] = None,
) -> bool:
    """
    Store veracity analysis result in Redshift.

    Args:
        article_id: Unique article identifier
        result: Veracity analysis result
        redshift_conn: Optional Redshift connection

    Returns:
        Success status
    """
    try:
        if redshift_conn is None:
            redshift_conn = RedshiftConnection()

        # Create table if not exists
        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {FakeNewsConfig.VERACITY_TABLE} (
            article_id VARCHAR(255) PRIMARY KEY,
            trustworthiness_score DECIMAL(5,2),
            classification VARCHAR(10),
            confidence DECIMAL(5,2),
            fake_probability DECIMAL(5,2),
            real_probability DECIMAL(5,2),
            model_used VARCHAR(100),
            analysis_timestamp TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        redshift_conn.execute_query(create_table_sql)

        # Insert or update veracity result
        insert_sql = f"""
        INSERT INTO {FakeNewsConfig.VERACITY_TABLE} 
        (article_id, trustworthiness_score, classification, confidence, 
         fake_probability, real_probability, model_used, analysis_timestamp)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (article_id) 
        DO UPDATE SET
            trustworthiness_score = EXCLUDED.trustworthiness_score,
            classification = EXCLUDED.classification,
            confidence = EXCLUDED.confidence,
            fake_probability = EXCLUDED.fake_probability,
            real_probability = EXCLUDED.real_probability,
            model_used = EXCLUDED.model_used,
            analysis_timestamp = EXCLUDED.analysis_timestamp,
            created_at = CURRENT_TIMESTAMP;
        """

        values = (
            article_id,
            result["trustworthiness_score"],
            result["classification"],
            result["confidence"],
            result["fake_probability"],
            result["real_probability"],
            result["model_used"],
            result["timestamp"],
        )

        redshift_conn.execute_query(insert_sql, values)
        logger.info(f"Stored veracity result for article {article_id}")
        return True

    except Exception as e:
        logger.error(f"Error storing veracity result: {e}")
        return False


@router.get("/news_veracity", response_model=VeracityResponse)
async def get_news_veracity(
    article_id: str = Query(..., description="Unique identifier for the article"),
    text: Optional[str] = Query(
        None, description="Article text for real-time analysis"
    ),
    force_recompute: bool = Query(
        False, description="Force recomputation even if cached"
    ),
):
    """
    Get trustworthiness analysis for a news article.
    """
    try:
        # Try to get cached result first (if not forcing recompute)
        cached_result = None
        if not force_recompute:
            try:
                redshift_conn = RedshiftConnection()
                query = f"""
                SELECT trustworthiness_score, classification, confidence,
                       fake_probability, real_probability, model_used,
                       analysis_timestamp
                FROM {FakeNewsConfig.VERACITY_TABLE}
                WHERE article_id = %s
                ORDER BY created_at DESC
                LIMIT 1;
                """
                result = redshift_conn.fetch_query(query, (article_id,))

                if result:
                    row = result[0]
                    cached_result = {
                        "trustworthiness_score": float(row[0]),
                        "classification": row[1],
                        "confidence": float(row[2]),
                        "fake_probability": float(row[3]),
                        "real_probability": float(row[4]),
                        "model_used": row[5],
                        "timestamp": row[6].isoformat() if row[6] else None,
                        "cached": True,
                    }
                    logger.info(
                        f"Retrieved cached veracity result for article {article_id}"
                    )

            except Exception as e:
                logger.warning(f"Could not retrieve cached result: {e}")

        # If we have cached result and not forcing recompute, return it
        if cached_result and not force_recompute:
            return VeracityResponse(
                article_id=article_id,
                veracity_analysis=cached_result,
                status="success",
                source="cache",
            )

        # Need to compute veracity analysis
        if not text:
            # Try to get article text from database
            try:
                redshift_conn = RedshiftConnection()
                query = """
                SELECT content, title 
                FROM articles 
                WHERE article_id = %s;
                """
                result = redshift_conn.fetch_query(query, (article_id,))

                if result:
                    content, title = result[0]
                    text = f"{title}. {content}" if title else content
                else:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Article {article_id} not found and no text provided",
                    )

            except Exception as e:
                raise HTTPException(
                    status_code=500, detail=f"Could not retrieve article text: {str(e)}"
                )

        # Perform veracity analysis
        detector = get_detector()
        veracity_result = detector.predict_trustworthiness(text)

        # Store result in database
        store_veracity_result(article_id, veracity_result)

        # Add metadata
        veracity_result["cached"] = False

        # Determine trust level
        score = veracity_result["trustworthiness_score"]
        if score >= FakeNewsConfig.HIGH_CONFIDENCE_THRESHOLD:
            trust_level = "high"
        elif score >= FakeNewsConfig.MEDIUM_CONFIDENCE_THRESHOLD:
            trust_level = "medium"
        else:
            trust_level = "low"

        veracity_result["trust_level"] = trust_level

        return VeracityResponse(
            article_id=article_id,
            veracity_analysis=veracity_result,
            status="success",
            source="computed",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in news veracity analysis: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch_veracity", response_model=BatchVeracityResponse)
async def batch_veracity_analysis(request: BatchVeracityRequest):
    """
    Perform veracity analysis on multiple articles.
    """
    try:
        detector = get_detector()
        results = []

        for article in request.articles:
            try:
                article_id = article.article_id
                text = article.text

                # Perform analysis
                veracity_result = detector.predict_trustworthiness(text)

                # Store result
                store_veracity_result(article_id, veracity_result)

                # Add metadata
                score = veracity_result["trustworthiness_score"]
                if score >= FakeNewsConfig.HIGH_CONFIDENCE_THRESHOLD:
                    trust_level = "high"
                elif score >= FakeNewsConfig.MEDIUM_CONFIDENCE_THRESHOLD:
                    trust_level = "medium"
                else:
                    trust_level = "low"

                veracity_result["trust_level"] = trust_level

                results.append(
                    {
                        "article_id": article_id,
                        "veracity_analysis": veracity_result,
                        "status": "success",
                    }
                )

            except Exception as e:
                logger.error(f"Error processing article {article.article_id}: {e}")
                results.append(
                    {
                        "article_id": article.article_id,
                        "error": str(e),
                        "status": "error",
                    }
                )

        return BatchVeracityResponse(
            results=results, total_processed=len(results), status="completed"
        )

    except Exception as e:
        logger.error(f"Error in batch veracity analysis: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/veracity_stats", response_model=StatisticsResponse)
async def get_veracity_statistics(
    days: int = Query(30, description="Number of days to look back")
):
    """
    Get statistics about veracity analysis results.
    """
    try:
        redshift_conn = RedshiftConnection()

        # Get overall statistics
        stats_query = f"""
        SELECT 
            COUNT(*) as total_articles,
            AVG(trustworthiness_score) as avg_trustworthiness,
            COUNT(CASE WHEN classification = 'real' THEN 1 END) as real_articles,
            COUNT(CASE WHEN classification = 'fake' THEN 1 END) as fake_articles,
            AVG(confidence) as avg_confidence
        FROM {FakeNewsConfig.VERACITY_TABLE}
        WHERE created_at >= CURRENT_DATE - INTERVAL '{days} days';
        """

        stats_result = redshift_conn.fetch_query(stats_query)

        if not stats_result:
            return StatisticsResponse(
                statistics={"message": "No veracity data found"}, status="success"
            )

        row = stats_result[0]
        statistics = {
            "total_articles_analyzed": int(row[0]) if row[0] else 0,
            "average_trustworthiness_score": round(float(row[1]), 2) if row[1] else 0,
            "real_articles_count": int(row[2]) if row[2] else 0,
            "fake_articles_count": int(row[3]) if row[3] else 0,
            "average_confidence": round(float(row[4]), 2) if row[4] else 0,
            "time_period_days": days,
        }

        # Calculate percentages
        total = statistics["total_articles_analyzed"]
        if total > 0:
            statistics["real_articles_percentage"] = round(
                (statistics["real_articles_count"] / total) * 100, 2
            )
            statistics["fake_articles_percentage"] = round(
                (statistics["fake_articles_count"] / total) * 100, 2
            )

        # Get distribution by trust level
        distribution_query = f"""
        SELECT 
            CASE 
                WHEN trustworthiness_score >= {FakeNewsConfig.HIGH_CONFIDENCE_THRESHOLD} THEN 'high'
                WHEN trustworthiness_score >= {FakeNewsConfig.MEDIUM_CONFIDENCE_THRESHOLD} THEN 'medium'
                ELSE 'low'
            END as trust_level,
            COUNT(*) as count
        FROM {FakeNewsConfig.VERACITY_TABLE}
        WHERE created_at >= CURRENT_DATE - INTERVAL '{days} days'
        GROUP BY trust_level;
        """

        distribution_result = redshift_conn.fetch_query(distribution_query)

        trust_distribution = {}
        for row in distribution_result:
            trust_distribution[row[0]] = int(row[1])

        statistics["trust_level_distribution"] = trust_distribution

        return StatisticsResponse(statistics=statistics, status="success")

    except Exception as e:
        logger.error(f"Error getting veracity statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/model_info", response_model=ModelInfoResponse)
async def get_model_info():
    """
    Get information about the fake news detection model.
    """
    try:
        detector = get_detector()

        model_info = {
            "model_name": detector.model_name,
            "device": str(detector.device),
            "model_type": "transformer",
            "task": "binary_classification",
            "labels": ["fake", "real"],
            "max_input_length": 512,
            "confidence_thresholds": {
                "high": FakeNewsConfig.HIGH_CONFIDENCE_THRESHOLD,
                "medium": FakeNewsConfig.MEDIUM_CONFIDENCE_THRESHOLD,
                "trustworthiness": FakeNewsConfig.TRUSTWORTHINESS_THRESHOLD,
            },
            "last_updated": datetime.now().isoformat(),
        }

        return ModelInfoResponse(model_info=model_info, status="success")

    except Exception as e:
        logger.error(f"Error getting model info: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
