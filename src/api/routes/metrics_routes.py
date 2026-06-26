"""
Resource metrics endpoints — Issue #334.

GET /metrics              last N samples (JSON or Prometheus text)
GET /metrics/summary      1h / 24h averages per metric
GET /metrics/current      live reading direct from psutil (no DB)
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

router = APIRouter(prefix="/metrics", tags=["monitoring"])


def _get_conn():
    from src.database.local_analytics_connector import get_shared_connection
    return get_shared_connection()


def _to_prometheus(rows: list) -> str:
    """Convert metric rows to Prometheus text exposition format."""
    # Group by metric_name for HELP/TYPE headers
    by_metric: Dict[str, list] = {}
    for r in rows:
        by_metric.setdefault(r["metric_name"], []).append(r)

    lines = []
    for metric_name, metric_rows in sorted(by_metric.items()):
        prom_name = f"neuronews_{metric_name}"
        unit = metric_rows[0]["unit"]
        lines.append(f"# HELP {prom_name} {metric_name} ({unit})")
        lines.append(f"# TYPE {prom_name} gauge")
        # Only emit the most recent sample per metric
        latest = metric_rows[0]
        label = ""
        if latest.get("process_name"):
            label = f'{{process="{latest["process_name"]}",pid="{latest["pid"]}"}}'
        lines.append(f"{prom_name}{label} {latest['value']}")
    return "\n".join(lines) + "\n"


@router.get("")
async def get_metrics(
    n: int = Query(100, ge=1, le=10_000, description="Max rows returned"),
    metric_name: Optional[str] = Query(None, description="Filter to one metric name"),
    since_minutes: Optional[int] = Query(None, ge=1, description="Only rows from last N minutes"),
    fmt: str = Query("json", description="Response format: json | prometheus"),
) -> Any:
    """
    Return recent resource metric samples.

    With ``fmt=prometheus`` the response is Prometheus text exposition format
    (one sample per metric — the most recent) so a local Prometheus scraper
    can consume it without any additional adapter.
    """
    try:
        from src.monitoring.resource_monitor import get_metrics as _get
        conn = _get_conn()
        rows = _get(conn, metric_name=metric_name, n=n, since_minutes=since_minutes)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if fmt == "prometheus":
        return PlainTextResponse(
            content=_to_prometheus(rows),
            media_type="text/plain; version=0.0.4",
        )
    return {"metrics": rows, "count": len(rows)}


@router.get("/summary")
async def get_metrics_summary() -> Dict[str, Any]:
    """
    Return 1-hour and 24-hour averages, min, and max for each metric.

    Returns an empty dict for windows with no stored data yet (the background
    collector writes every 60 s, so the first sample appears within a minute
    of startup).
    """
    try:
        from src.monitoring.resource_monitor import get_summary
        conn = _get_conn()
        return get_summary(conn)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/current")
async def get_current_metrics() -> Dict[str, Any]:
    """
    Return a live psutil reading — no database involved.

    Useful for health checks and dashboards that need the instant value
    rather than a historical sample.
    """
    try:
        from src.monitoring.resource_monitor import collect_sample
        rows = collect_sample()
        return {
            r["metric_name"]: {"value": r["value"], "unit": r["unit"]}
            for r in rows
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
