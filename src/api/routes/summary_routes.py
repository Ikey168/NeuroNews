"""
FastAPI routes for AI-powered article summarization.

This module provides RESTful API endpoints for generating and retrieving
AI-powered article summaries with support for different lengths and models.

Endpoints:
- POST /summarize - Generate new summary
- GET /summarize/{article_id} - Get existing summaries
- GET /summarize/{article_id}/{length} - Get specific summary
- DELETE /summarize/{article_id} - Delete summaries
- GET /summarize/stats - Get summarization statistics

Author: NeuroNews Development Team
Created: August 2025
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path
from pydantic import BaseModel, Field, validator
from starlette.status import HTTP_201_CREATED, HTTP_404_NOT_FOUND

from ..nlp.ai_summarizer import (
    AIArticleSummarizer,
    SummarizationModel,
    SummaryLength,
)
from ..nlp.summary_database import (
    SummaryDatabase,
    get_redshift_connection_params,
)

logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(prefix="/api/v1/summarize", tags=["summarization"])

# Global summarizer instance (will be initialized on startup)
_summarizer: Optional[AIArticleSummarizer] = None
_summary_db: Optional[SummaryDatabase] = None


# Pydantic models for API
class SummarizationRequest(BaseModel):
    """Request model for article summarization."""

    article_id: str = Field(..., description="Unique identifier for the article")
    text: str = Field(..., min_length=100, description="Article text to summarize")
    length: Optional[SummaryLength] = Field(
        SummaryLength.MEDIUM, description="Desired summary length"
    )
    model: Optional[SummarizationModel] = Field(
        None, description="Specific model to use"
    )
    force_regenerate: bool = Field(
        False, description="Force regeneration even if summary exists"
    )

    @validator("text")
    def validate_text(cls, v):
        if len(v.strip()) < 100:
            raise ValueError("Text must be at least 100 characters long")
        return v.strip()


class SummarizationResponse(BaseModel):
    """Response model for summarization."""

    article_id: str
    summary_id: int
    summary_text: str
    length: str
    model: str
    confidence_score: float
    processing_time: float
    word_count: int
    sentence_count: int
    compression_ratio: float
    created_at: str
    from_cache: bool = False


class BatchSummarizationRequest(BaseModel):
    """Request model for batch summarization."""

    articles: List[SummarizationRequest] = Field(
        ..., max_items=10, description="Articles to summarize (max 10)"
    )


class BatchSummarizationResponse(BaseModel):
    """Response model for batch summarization."""

    results: List[SummarizationResponse]
    total_articles: int
    successful: int
    failed: int
    total_processing_time: float


class SummaryStatistics(BaseModel):
    """Model for summary statistics."""

    total_summaries: int
    unique_articles: int
    avg_confidence: float
    avg_processing_time: float
    avg_word_count: float
    avg_compression_ratio: float
    by_length: Dict[str, Dict[str, Any]]
    cache_stats: Dict[str, Any]


# Dependency functions
async def get_summarizer() -> AIArticleSummarizer:
    """Get the global summarizer instance."""
    global _summarizer
    if _summarizer is None:
        _summarizer = AIArticleSummarizer()
    return _summarizer


async def get_summary_database() -> SummaryDatabase:
    """Get the global summary database instance."""
    global _summary_db
    if _summary_db is None:
        connection_params = get_redshift_connection_params()
        _summary_db = SummaryDatabase(connection_params)
        await _summary_db.create_table()
    return _summary_db


# API Routes
@router.post("/", response_model=SummarizationResponse, status_code=HTTP_201_CREATED)
async def generate_summary(
    request: SummarizationRequest,
    background_tasks: BackgroundTasks,
    summarizer: AIArticleSummarizer = Depends(get_summarizer),
    db: SummaryDatabase = Depends(get_summary_database),
):
    """
    Generate an AI-powered summary for an article.

    Args:
        request: Summarization request parameters
        background_tasks: FastAPI background tasks
        summarizer: AI summarizer instance
        db: Summary database instance

    Returns:
        Generated summary response

    Raises:
        HTTPException: If summarization fails
    """
    start_time = time.time()

    try:
        # Check if summary already exists (unless force regenerate)
        if not request.force_regenerate:
            from_cache = False
            existing = await db.get_summary_by_article_and_length(
                request.article_id, request.length
            )

            if existing:
                logger.info(
                    "Returning cached summary for article {0}".format(
                        request.article_id)
                )
                return SummarizationResponse(
                    article_id=existing.article_id,
                    summary_id=existing.id,
                    summary_text=existing.summary_text,
                    length=existing.summary_length,
                    model=existing.model_used,
                    confidence_score=existing.confidence_score,
                    processing_time=existing.processing_time,
                    word_count=existing.word_count,
                    sentence_count=existing.sentence_count,
                    compression_ratio=existing.compression_ratio,
                    created_at=(
                        existing.created_at.isoformat() if existing.created_at else ""
                    ),
                    from_cache=True,
                )

        # Generate new summary
        logger.info(
            "Generating {0} summary for article {1}".format(
                request.length.value, 
                request.article_id)
        )
        summary = await summarizer.summarize_article(
            text=request.text, length=request.length, model=request.model
        )

        # Store in database
        summary_id = await db.store_summary(
            article_id=request.article_id, original_text=request.text, summary=summary
        )

        processing_time = time.time() - start_time

        logger.info(
            "Summary generated and stored with ID {0} in {1:.2f}s".format(
                summary_id, processing_time
            )
        )

        return SummarizationResponse(
            article_id=request.article_id,
            summary_id=summary_id,
            summary_text=summary.text,
            length=summary.length.value,
            model=summary.model.value,
            confidence_score=summary.confidence_score,
            processing_time=summary.processing_time,
            word_count=summary.word_count,
            sentence_count=summary.sentence_count,
            compression_ratio=summary.compression_ratio,
            created_at=summary.created_at,
            from_cache=False,
        )

    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(
            "Summarization failed after {0}s: {1}".format(
                processing_time:.2f, 
                str(e))
        )
        raise HTTPException(
            status_code=500,
            detail="Summarization failed: {0}".format(
                str(e)),
        )


@router.post("/batch", response_model=BatchSummarizationResponse)
async def generate_batch_summaries(
    request: BatchSummarizationRequest,
    background_tasks: BackgroundTasks,
    summarizer: AIArticleSummarizer = Depends(get_summarizer),
    db: SummaryDatabase = Depends(get_summary_database),
):
    """
    Generate summaries for multiple articles in batch.

    Args:
        request: Batch summarization request
        background_tasks: FastAPI background tasks
        summarizer: AI summarizer instance
        db: Summary database instance

    Returns:
        Batch summarization results
    """
    start_time = time.time()
    results = []
    successful = 0
    failed = 0

    logger.info("Processing batch of {0} articles".format(len(request.articles)))

    # Process articles concurrently (with reasonable limit)
    semaphore = asyncio.Semaphore(3)  # Limit concurrent processing

    async def process_article(article_request: SummarizationRequest):
        nonlocal successful, failed

        async with semaphore:
            try:
                # Check cache first
                if not article_request.force_regenerate:
                    existing = await db.get_summary_by_article_and_length(
                        article_request.article_id, article_request.length
                    )

                    if existing:
                        successful += 1
                        return SummarizationResponse(
                            article_id=existing.article_id,
                            summary_id=existing.id,
                            summary_text=existing.summary_text,
                            length=existing.summary_length,
                            model=existing.model_used,
                            confidence_score=existing.confidence_score,
                            processing_time=existing.processing_time,
                            word_count=existing.word_count,
                            sentence_count=existing.sentence_count,
                            compression_ratio=existing.compression_ratio,
                            created_at=(
                                existing.created_at.isoformat()
                                if existing.created_at
                                else ""
                            ),
                            from_cache=True,
                        )

                # Generate new summary
                summary = await summarizer.summarize_article(
                    text=article_request.text,
                    length=article_request.length,
                    model=article_request.model,
                )

                # Store in database
                summary_id = await db.store_summary(
                    article_id=article_request.article_id,
                    original_text=article_request.text,
                    summary=summary,
                )

                successful += 1
                return SummarizationResponse(
                    article_id=article_request.article_id,
                    summary_id=summary_id,
                    summary_text=summary.text,
                    length=summary.length.value,
                    model=summary.model.value,
                    confidence_score=summary.confidence_score,
                    processing_time=summary.processing_time,
                    word_count=summary.word_count,
                    sentence_count=summary.sentence_count,
                    compression_ratio=summary.compression_ratio,
                    created_at=summary.created_at,
                    from_cache=False,
                )

            except Exception as e:
                failed += 1
                logger.error(
                    "Failed to process article {0}: {1}".format(
                        article_request.article_id, 
                        str(e))
                )
                return None

    # Process all articles
    tasks = [process_article(article) for article in request.articles]
    task_results = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter successful results
    results = [result for result in task_results if result is not None]

    total_processing_time = time.time() - start_time

    logger.info(
        "Batch processing completed: {0} successful, ".format(successful)
        "{0} failed in {1}s".format(failed, total_processing_time)
    )

    return BatchSummarizationResponse(
        results=results,
        total_articles=len(request.articles),
        successful=successful,
        failed=failed,
        total_processing_time=total_processing_time,
    )


@router.get("/{article_id}", response_model=List[SummarizationResponse])
async def get_article_summaries(
    article_id: str = Path(..., description="Article ID"),
    db: SummaryDatabase = Depends(get_summary_database),
):
    """
    Get all summaries for a specific article.

    Args:
        article_id: Unique identifier for the article
        db: Summary database instance

    Returns:
        List of summaries for the article

    Raises:
        HTTPException: If article not found or database error
    """
    try:
        summaries = await db.get_summaries_by_article(article_id)

        if not summaries:
            raise HTTPException(
                status_code=HTTP_404_NOT_FOUND,
                detail="No summaries found for article {0}".format(article_id),
            )

        return [
            SummarizationResponse(
                article_id=summary.article_id,
                summary_id=summary.id,
                summary_text=summary.summary_text,
                length=summary.summary_length,
                model=summary.model_used,
                confidence_score=summary.confidence_score,
                processing_time=summary.processing_time,
                word_count=summary.word_count,
                sentence_count=summary.sentence_count,
                compression_ratio=summary.compression_ratio,
                created_at=summary.created_at.isoformat() if summary.created_at else "",
                from_cache=True,
            )
            for summary in summaries
        ]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to get summaries for article {0}: {1}".format(article_id, 
                str(e))
        )
        raise HTTPException(
            status_code=500, detail="Failed to retrieve summaries: {0}".format(str(e))
        )


@router.get("/{article_id}/{length}", response_model=SummarizationResponse)
async def get_specific_summary(
    article_id: str = Path(..., description="Article ID"),
    length: SummaryLength = Path(..., description="Summary length"),
    db: SummaryDatabase = Depends(get_summary_database),
):
    """
    Get a specific summary by article ID and length.

    Args:
        article_id: Unique identifier for the article
        length: Desired summary length
        db: Summary database instance

    Returns:
        Specific summary response

    Raises:
        HTTPException: If summary not found or database error
    """
    try:
        summary = await db.get_summary_by_article_and_length(article_id, length)

        if not summary:
            raise HTTPException(
                status_code=HTTP_404_NOT_FOUND,
                detail="No {0} summary found for article {1}".format(
                    length.value, article_id),
            )

        return SummarizationResponse(
            article_id=summary.article_id,
            summary_id=summary.id,
            summary_text=summary.summary_text,
            length=summary.summary_length,
            model=summary.model_used,
            confidence_score=summary.confidence_score,
            processing_time=summary.processing_time,
            word_count=summary.word_count,
            sentence_count=summary.sentence_count,
            compression_ratio=summary.compression_ratio,
            created_at=summary.created_at.isoformat() if summary.created_at else "",
            from_cache=True,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to get {0} summary for article {1}: {2}".format(
                length.value, article_id, 
                str(e))
        )
        raise HTTPException(
            status_code=500, detail="Failed to retrieve summary: {0}".format(str(e))
        )


@router.delete("/{article_id}")
async def delete_article_summaries(
    article_id: str = Path(..., description="Article ID"),
    db: SummaryDatabase = Depends(get_summary_database),
):
    """
    Delete all summaries for a specific article.

    Args:
        article_id: Unique identifier for the article
        db: Summary database instance

    Returns:
        Deletion result

    Raises:
        HTTPException: If deletion fails
    """
    try:
        deleted_count = await db.delete_summaries_by_article(article_id)

        if deleted_count == 0:
            raise HTTPException(
                status_code=HTTP_404_NOT_FOUND,
                detail="No summaries found for article {0}".format(article_id),
            )

        return {
            "message": "Deleted {0} summaries for article {1}".format(deleted_count, article_id),
            "deleted_count": deleted_count,
            "article_id": article_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to delete summaries for article {0}: {1}".format(article_id, 
                str(e))
        )
        raise HTTPException(
            status_code=500, detail="Failed to delete summaries: {0}".format(str(e))
        )


@router.get("/stats/overview", response_model=SummaryStatistics)
async def get_summarization_statistics(
    db: SummaryDatabase = Depends(get_summary_database),
    summarizer: AIArticleSummarizer = Depends(get_summarizer),
):
    """
    Get comprehensive summarization statistics.

    Args:
        db: Summary database instance
        summarizer: AI summarizer instance

    Returns:
        Summary statistics

    Raises:
        HTTPException: If statistics retrieval fails
    """
    try:
        # Get database statistics
        db_stats = await db.get_summary_statistics()

        # Get summarizer performance metrics
        summarizer_info = summarizer.get_model_info()

        # Combine statistics
        total_stats = db_stats.get("total", {})
        by_length = {k: v for k, v in db_stats.items() if k != "total" and k != "cache"}

        return SummaryStatistics(
            total_summaries=total_stats.get("total_summaries", 0),
            unique_articles=total_stats.get("unique_articles", 0),
            avg_confidence=total_stats.get("avg_confidence", 0.0),
            avg_processing_time=total_stats.get("avg_processing_time", 0.0),
            avg_word_count=total_stats.get("avg_word_count", 0.0),
            avg_compression_ratio=total_stats.get("avg_compression_ratio", 0.0),
            by_length=by_length,
            cache_stats={
                **db_stats.get("cache", {}),
                "summarizer_metrics": summarizer_info["metrics"],
            },
        )

    except Exception as e:
        logger.error("Failed to get summarization statistics: {0}".format(str(e)))
        raise HTTPException(
            status_code=500, detail="Failed to retrieve statistics: {0}".format(str(e))
        )


@router.post("/cache/clear")
async def clear_caches(
    db: SummaryDatabase = Depends(get_summary_database),
    summarizer: AIArticleSummarizer = Depends(get_summarizer),
):
    """
    Clear all caches (database and model caches).

    Args:
        db: Summary database instance
        summarizer: AI summarizer instance

    Returns:
        Cache clearing result
    """
    try:
        # Clear database cache
        db.clear_cache()

        # Clear model cache
        summarizer.clear_cache()

        return {
            "message": "All caches cleared successfully",
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error("Failed to clear caches: {0}".format(str(e)))
        raise HTTPException(
            status_code=500,
            detail="Failed to clear caches: {0}".format(
                str(e)),
        )


@router.get("/models/info")
async def get_model_information(
    summarizer: AIArticleSummarizer = Depends(get_summarizer),
):
    """
    Get information about available summarization models.

    Args:
        summarizer: AI summarizer instance

    Returns:
        Model information and configuration
    """
    try:
        model_info = summarizer.get_model_info()

        return {
            "available_models": [model.value for model in SummarizationModel],
            "available_lengths": [length.value for length in SummaryLength],
            "current_config": model_info,
            "device": model_info.get("device", "unknown"),
        }

    except Exception as e:
        logger.error("Failed to get model information: {0}".format(str(e)))
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve model information: {0}".format(
                str(e)),
        )


# Health check endpoint
@router.get("/health")
async def health_check():
    """Health check endpoint for the summarization service."""
    return {
        "status": "healthy",
        "service": "AI Article Summarization",
        "timestamp": datetime.now().isoformat(),
    }
