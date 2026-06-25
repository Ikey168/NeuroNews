"""
Report generation and scheduled delivery routes (Issues #51, #52, #54).

GET  /api/v1/reports/generate              — on-demand report (json | csv | pdf)
GET  /api/v1/reports/custom_report         — customisable report (entity, date_range, sentiment …)
POST /api/v1/reports/subscribe             — create a scheduled email subscription
GET  /api/v1/reports/subscriptions         — list subscriptions (?email=...)
GET  /api/v1/reports/subscriptions/{id}    — single subscription + delivery stats
DELETE /api/v1/reports/subscriptions/{id}  — unsubscribe
POST /api/v1/reports/schedules             — create a custom scheduled report
GET  /api/v1/reports/schedules             — list custom schedules (?email=...)
DELETE /api/v1/reports/schedules/{id}      — delete a custom schedule
POST /api/v1/reports/trigger/{frequency}   — manually fire weekly|monthly delivery
GET  /api/v1/reports/track/open/{token}    — 1×1 tracking pixel (open event)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, field_validator

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

_VALID_PERIODS = {"last_7_days", "last_30_days", "last_90_days", "last_24_hours"}


@router.get("/generate")
async def generate_report(
    topic: str = Query(..., min_length=1, description="Topic keyword to search for"),
    period: str = Query("last_7_days", description="Time window for the report"),
    format: str = Query("json", description="Output format: json | csv | pdf"),
) -> Any:
    """
    Generate a topic report from the analytics warehouse.

    Returns JSON summary stats, or streams a CSV/PDF file for download.
    """
    if period not in _VALID_PERIODS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid period '{period}'. Valid options: {sorted(_VALID_PERIODS)}",
        )
    if format not in ("json", "csv", "pdf"):
        raise HTTPException(
            status_code=422,
            detail="Invalid format. Use: json, csv, or pdf",
        )

    try:
        if format == "csv":
            from src.reports.generate_report import generate_csv
            data = generate_csv(topic, period)
            filename = f"report_{topic.lower().replace(' ', '_')}_{period}.csv"
            return Response(
                content=data,
                media_type="text/csv",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        if format == "pdf":
            from src.reports.generate_report import generate_pdf
            data = generate_pdf(topic, period)
            filename = f"report_{topic.lower().replace(' ', '_')}_{period}.pdf"
            return Response(
                content=data,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        # JSON: return stats + article list
        from src.reports.generate_report import _fetch_report_data
        report = _fetch_report_data(topic, period)
        return {
            "topic": report.topic,
            "period": report.period,
            "generated_at": report.generated_at,
            "stats": {
                "total_articles": report.total_articles,
                "avg_sentiment": report.avg_sentiment,
                "positive_pct": report.positive_pct,
                "negative_pct": report.negative_pct,
                "neutral_pct": report.neutral_pct,
                "top_sources": report.top_sources,
            },
            "articles": [
                {
                    "article_id": a.article_id,
                    "title": a.title,
                    "source": a.source,
                    "category": a.category,
                    "publish_date": a.publish_date,
                    "sentiment_label": a.sentiment_label,
                    "sentiment_score": a.sentiment_score,
                    "url": a.url,
                }
                for a in report.articles
            ],
        }

    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Report generation failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Subscription request model
# ---------------------------------------------------------------------------

_VALID_FREQUENCIES = {"weekly", "monthly"}
_VALID_FORMATS = {"pdf", "csv"}


class SubscribeRequest(BaseModel):
    email: str
    topic: str
    frequency: str = "weekly"
    format: str = "pdf"

    @field_validator("frequency")
    @classmethod
    def check_frequency(cls, v: str) -> str:
        if v not in _VALID_FREQUENCIES:
            raise ValueError(f"frequency must be one of {sorted(_VALID_FREQUENCIES)}")
        return v

    @field_validator("format")
    @classmethod
    def check_format(cls, v: str) -> str:
        if v not in _VALID_FORMATS:
            raise ValueError(f"format must be one of {sorted(_VALID_FORMATS)}")
        return v


# ---------------------------------------------------------------------------
# Subscription endpoints
# ---------------------------------------------------------------------------

@router.post("/subscribe", status_code=201)
async def subscribe(body: SubscribeRequest) -> Dict[str, Any]:
    """Subscribe an email address to periodic report delivery."""
    try:
        from src.reports.subscriptions import create_subscription
        sub = create_subscription(body.email, body.topic, body.frequency, body.format)
        return {"status": "created", "subscription": sub}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/subscriptions")
async def list_subscriptions(
    email: Optional[str] = Query(None, description="Filter by subscriber email"),
) -> Dict[str, Any]:
    """List all subscriptions, optionally filtered by email."""
    try:
        from src.reports.subscriptions import list_subscriptions as _list
        return {"subscriptions": _list(email)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/subscriptions/{sub_id}")
async def get_subscription(sub_id: str) -> Dict[str, Any]:
    """Get a single subscription and its delivery stats."""
    try:
        from src.reports.subscriptions import get_subscription as _get, delivery_stats
        sub = _get(sub_id)
        if sub is None:
            raise HTTPException(status_code=404, detail=f"Subscription '{sub_id}' not found")
        return {"subscription": sub, "delivery_stats": delivery_stats(sub_id)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/subscriptions/{sub_id}", status_code=200)
async def unsubscribe(sub_id: str) -> Dict[str, Any]:
    """Remove a subscription."""
    try:
        from src.reports.subscriptions import get_subscription as _get, delete_subscription
        if _get(sub_id) is None:
            raise HTTPException(status_code=404, detail=f"Subscription '{sub_id}' not found")
        delete_subscription(sub_id)
        return {"status": "deleted", "id": sub_id}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Manual trigger (for testing / admin use)
# ---------------------------------------------------------------------------

@router.post("/trigger/{frequency}")
async def trigger_delivery(frequency: str) -> Dict[str, Any]:
    """Manually fire a delivery run (weekly | monthly). For testing only."""
    if frequency not in _VALID_FREQUENCIES:
        raise HTTPException(
            status_code=422,
            detail=f"frequency must be one of {sorted(_VALID_FREQUENCIES)}",
        )
    try:
        from src.reports.scheduler import trigger_now
        count = trigger_now(frequency)
        return {"status": "triggered", "frequency": frequency, "subscriptions_processed": count}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Open tracking pixel
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Custom report endpoint (issue #54)
# ---------------------------------------------------------------------------

_VALID_SENTIMENTS = {"positive", "negative", "neutral", "all"}
_VALID_PERIODS_EXT = {"last_24_hours", "last_7_days", "last_30_days", "last_60_days", "last_90_days"}


@router.get("/custom_report")
async def custom_report(
    entity: Optional[str] = Query(None, description="Primary entity/keyword (alias for keywords[0])"),
    keywords: Optional[str] = Query(None, description="Comma-separated additional keywords"),
    date_range: Optional[str] = Query(None, description="Preset: last_7_days | last_30_days | last_60_days | last_90_days | last_24_hours"),
    date_from: Optional[str] = Query(None, description="ISO date start, e.g. 2026-01-01"),
    date_to: Optional[str] = Query(None, description="ISO date end, e.g. 2026-06-30"),
    sentiment: Optional[str] = Query(None, description="positive | negative | neutral | all"),
    sentiment_min: Optional[float] = Query(None, ge=-1.0, le=1.0, description="Min sentiment score"),
    sentiment_max: Optional[float] = Query(None, ge=-1.0, le=1.0, description="Max sentiment score"),
    source: Optional[str] = Query(None, description="Filter by source name (ILIKE)"),
    category: Optional[str] = Query(None, description="Filter by category (ILIKE)"),
    format: str = Query("json", description="json | csv | pdf"),
    limit: int = Query(200, ge=1, le=1000),
    title: Optional[str] = Query(None, description="Custom report title"),
) -> Any:
    """
    Fully customisable report with entity/keyword, date range, and sentiment filters.

    Example: /api/v1/reports/custom_report?entity=Tesla&date_range=last_60_days&sentiment=negative
    """
    # Build keyword list
    kw_list: List[str] = []
    if entity:
        kw_list.append(entity)
    if keywords:
        kw_list.extend([k.strip() for k in keywords.split(",") if k.strip()])
    if not kw_list:
        raise HTTPException(status_code=422, detail="Provide at least one of: entity, keywords")

    if date_range and date_range not in _VALID_PERIODS_EXT:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid date_range. Valid: {sorted(_VALID_PERIODS_EXT)}",
        )
    if sentiment and sentiment not in _VALID_SENTIMENTS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid sentiment. Valid: {sorted(_VALID_SENTIMENTS)}",
        )
    if format not in ("json", "csv", "pdf"):
        raise HTTPException(status_code=422, detail="format must be json | csv | pdf")

    try:
        from src.reports.generate_report import (
            CustomReportFilter, fetch_custom_report_data,
            generate_custom_csv, generate_custom_pdf,
        )

        filt = CustomReportFilter(
            keywords=kw_list,
            period=date_range,
            date_from=date_from,
            date_to=date_to,
            sentiment=sentiment if sentiment != "all" else None,
            sentiment_min=sentiment_min,
            sentiment_max=sentiment_max,
            source=source,
            category=category,
            limit=limit,
            report_title=title or "",
        )

        slug = "_".join(kw_list[:2]).lower().replace(" ", "_")

        if format == "csv":
            data = generate_custom_csv(filt)
            filename = f"custom_report_{slug}.csv"
            return Response(
                content=data, media_type="text/csv",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        if format == "pdf":
            data = generate_custom_pdf(filt)
            filename = f"custom_report_{slug}.pdf"
            return Response(
                content=data, media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        report = fetch_custom_report_data(filt)
        return {
            "topic": report.topic,
            "period": report.period,
            "generated_at": report.generated_at,
            "filters_applied": {
                "keywords": kw_list,
                "date_range": date_range,
                "date_from": date_from,
                "date_to": date_to,
                "sentiment": sentiment,
                "sentiment_min": sentiment_min,
                "sentiment_max": sentiment_max,
                "source": source,
                "category": category,
                "limit": limit,
            },
            "stats": {
                "total_articles": report.total_articles,
                "avg_sentiment": report.avg_sentiment,
                "positive_pct": report.positive_pct,
                "negative_pct": report.negative_pct,
                "neutral_pct": report.neutral_pct,
                "top_sources": report.top_sources,
            },
            "articles": [
                {
                    "article_id": a.article_id,
                    "title": a.title,
                    "source": a.source,
                    "category": a.category,
                    "publish_date": a.publish_date,
                    "sentiment_label": a.sentiment_label,
                    "sentiment_score": a.sentiment_score,
                    "url": a.url,
                }
                for a in report.articles
            ],
        }

    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Custom report failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Custom schedule endpoints (issue #54)
# ---------------------------------------------------------------------------

_VALID_FREQUENCIES = {"weekly", "monthly"}
_VALID_FORMATS = {"pdf", "csv"}


class CustomScheduleRequest(BaseModel):
    name: str
    email: str
    frequency: str = "weekly"
    format: str = "pdf"
    keywords: List[str]
    date_range: Optional[str] = None
    sentiment: Optional[str] = None
    sentiment_min: Optional[float] = None
    sentiment_max: Optional[float] = None
    source: Optional[str] = None
    category: Optional[str] = None
    limit: int = 200

    @field_validator("frequency")
    @classmethod
    def check_freq(cls, v: str) -> str:
        if v not in _VALID_FREQUENCIES:
            raise ValueError(f"frequency must be one of {sorted(_VALID_FREQUENCIES)}")
        return v

    @field_validator("format")
    @classmethod
    def check_fmt(cls, v: str) -> str:
        if v not in _VALID_FORMATS:
            raise ValueError(f"format must be one of {sorted(_VALID_FORMATS)}")
        return v

    @field_validator("keywords")
    @classmethod
    def check_keywords(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("At least one keyword required")
        return v

    model_config = {"arbitrary_types_allowed": True}


CustomScheduleRequest.model_rebuild()


@router.post("/schedules", status_code=201)
async def create_schedule(body: CustomScheduleRequest) -> Dict[str, Any]:
    """Create a custom scheduled report with filter configuration."""
    try:
        from src.reports.subscriptions import create_custom_schedule
        filters = {
            "keywords": body.keywords,
            "period": body.date_range,
            "sentiment": body.sentiment,
            "sentiment_min": body.sentiment_min,
            "sentiment_max": body.sentiment_max,
            "source": body.source,
            "category": body.category,
            "limit": body.limit,
        }
        sched = create_custom_schedule(
            name=body.name,
            email=body.email,
            frequency=body.frequency,
            fmt=body.format,
            filters=filters,
        )
        return {"status": "created", "schedule": sched}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/schedules")
async def list_schedules(
    email: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """List custom report schedules."""
    try:
        from src.reports.subscriptions import list_custom_schedules
        return {"schedules": list_custom_schedules(email)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/schedules/{sched_id}")
async def delete_schedule(sched_id: str) -> Dict[str, Any]:
    """Delete a custom report schedule."""
    try:
        from src.reports.subscriptions import get_custom_schedule, delete_custom_schedule
        if get_custom_schedule(sched_id) is None:
            raise HTTPException(status_code=404, detail=f"Schedule '{sched_id}' not found")
        delete_custom_schedule(sched_id)
        return {"status": "deleted", "id": sched_id}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Open tracking pixel
# ---------------------------------------------------------------------------

_TRACKING_PIXEL = (
    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff"
    b"\x00\x00\x00\x21\xf9\x04\x00\x00\x00\x00\x00\x2c\x00\x00\x00\x00"
    b"\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b"
)


@router.get("/track/open/{token}", include_in_schema=False)
async def track_open(token: str) -> Response:
    """Record an email open event and return a 1×1 transparent GIF."""
    try:
        from src.reports.subscriptions import record_open
        record_open(token)
    except Exception:
        pass  # never fail a tracking request
    return Response(
        content=_TRACKING_PIXEL,
        media_type="image/gif",
        headers={"Cache-Control": "no-store, no-cache"},
    )
