"""
Report generation routes (Issue #51).

GET /api/v1/reports/generate
    ?topic=AI+Ethics
    &period=last_30_days   (last_7_days | last_30_days | last_90_days | last_24_hours)
    &format=json           (json | csv | pdf)

JSON returns headline stats + first-page article list.
CSV / PDF stream the file as a download.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

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
