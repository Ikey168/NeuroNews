"""
Real-time alert routes (Issue #53).

POST   /api/v1/alerts/rules             — create an alert rule
GET    /api/v1/alerts/rules             — list all rules
GET    /api/v1/alerts/rules/{id}        — get one rule
DELETE /api/v1/alerts/rules/{id}        — delete a rule
POST   /api/v1/alerts/poll              — manually trigger a poll cycle
GET    /api/v1/alerts/history           — recent fired alerts
GET    /api/v1/alerts/stream            — SSE stream of live alert events
POST   /api/v1/alerts/test/{channel}    — send a test alert to one channel
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])

_VALID_TYPES = {"breaking_news", "sentiment_shift", "new_event"}
_VALID_CHANNELS = {"email", "slack", "telegram"}


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------

class AlertRuleRequest(BaseModel):
    name: str
    topic: str
    alert_type: str
    channels: List[str]
    email: Optional[str] = None
    threshold: Optional[float] = None
    cooldown_min: int = 60

    @field_validator("alert_type")
    @classmethod
    def check_type(cls, v: str) -> str:
        if v not in _VALID_TYPES:
            raise ValueError(f"alert_type must be one of {sorted(_VALID_TYPES)}")
        return v

    @field_validator("channels")
    @classmethod
    def check_channels(cls, v: List[str]) -> List[str]:
        bad = set(v) - _VALID_CHANNELS
        if bad:
            raise ValueError(f"Unknown channels: {sorted(bad)}. Valid: {sorted(_VALID_CHANNELS)}")
        if not v:
            raise ValueError("At least one channel required")
        return v

    model_config = {"arbitrary_types_allowed": True}


AlertRuleRequest.model_rebuild()


# ---------------------------------------------------------------------------
# Rules endpoints
# ---------------------------------------------------------------------------

@router.post("/rules", status_code=201)
async def create_rule(body: AlertRuleRequest) -> Dict[str, Any]:
    """Create a new alert rule."""
    try:
        from src.alerts.store import create_rule as _create
        rule = _create(
            name=body.name,
            topic=body.topic,
            alert_type=body.alert_type,
            channels=body.channels,
            email=body.email,
            threshold=body.threshold,
            cooldown_min=body.cooldown_min,
        )
        return {"status": "created", "rule": rule}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/rules")
async def list_rules() -> Dict[str, Any]:
    """List all alert rules."""
    try:
        from src.alerts.store import list_rules as _list
        return {"rules": _list()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/rules/{rule_id}")
async def get_rule(rule_id: str) -> Dict[str, Any]:
    """Get a single alert rule."""
    try:
        from src.alerts.store import get_rule as _get
        rule = _get(rule_id)
        if rule is None:
            raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
        return {"rule": rule}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str) -> Dict[str, Any]:
    """Delete an alert rule."""
    try:
        from src.alerts.store import get_rule as _get, delete_rule as _delete
        if _get(rule_id) is None:
            raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
        _delete(rule_id)
        return {"status": "deleted", "id": rule_id}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Manual poll + history
# ---------------------------------------------------------------------------

@router.post("/poll")
async def manual_poll() -> Dict[str, Any]:
    """Manually trigger a poll cycle across all rules. Returns fired alerts."""
    try:
        from src.alerts.dispatcher import poll_and_dispatch
        fired = poll_and_dispatch()
        return {"alerts_fired": len(fired), "alerts": fired}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/history")
async def get_history(
    limit: int = Query(50, ge=1, le=500),
) -> Dict[str, Any]:
    """Get recently fired alert history."""
    try:
        from src.alerts.store import get_history as _hist
        return {"history": _hist(limit=limit)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# SSE stream
# ---------------------------------------------------------------------------

@router.get("/stream")
async def alert_stream() -> StreamingResponse:
    """
    Server-Sent Events stream of live alerts.

    Connect with:
        const es = new EventSource('/api/v1/alerts/stream');
        es.onmessage = e => console.log(JSON.parse(e.data));
    """
    from src.alerts.dispatcher import register_sse_client, unregister_sse_client

    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    register_sse_client(q)

    async def _generate():
        try:
            # Initial keep-alive comment
            yield ": connected\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    # keep-alive ping
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            unregister_sse_client(q)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Channel test
# ---------------------------------------------------------------------------

@router.post("/test/{channel}")
async def test_channel(
    channel: str,
    email: Optional[str] = Query(None, description="Required when channel=email"),
) -> Dict[str, Any]:
    """Send a test alert to verify a channel is configured correctly."""
    if channel not in _VALID_CHANNELS:
        raise HTTPException(
            status_code=422,
            detail=f"channel must be one of {sorted(_VALID_CHANNELS)}",
        )
    if channel == "email" and not email:
        raise HTTPException(status_code=422, detail="?email= required for email channel test")

    from src.alerts.channels import dispatch
    results = dispatch(
        [channel],
        title="Noesis Alert Test",
        body="This is a test alert from the Noesis real-time alert system. If you received this, the channel is configured correctly.",
        email=email,
    )
    ok = results.get(channel, False)
    return {"channel": channel, "delivered": ok, "note": "" if ok else "Check server logs and env vars"}
