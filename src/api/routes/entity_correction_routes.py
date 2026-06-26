"""
Entity correction routes — Issue #44.

Trusted users (PREMIUM+) submit corrections; admins approve or reject them.

User endpoints  (require READ_KNOWLEDGE_GRAPH permission):
  GET  /entities/{entity_id}                          entity details from live KG
  POST /entities/{entity_id}/corrections              submit a correction
  GET  /entities/{entity_id}/corrections              correction history for entity

Admin endpoints  (require UPDATE_KNOWLEDGE_GRAPH permission):
  GET  /admin/entity-corrections                      all pending corrections
  GET  /admin/entity-corrections/{correction_id}      single correction detail
  POST /admin/entity-corrections/{correction_id}/approve   approve + apply
  POST /admin/entity-corrections/{correction_id}/reject    reject
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.auth.jwt_auth import require_auth

router = APIRouter(tags=["entity-corrections"])


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _require_trusted(user: dict = Depends(require_auth)) -> dict:
    """PREMIUM or ADMIN users may submit corrections."""
    role = user.get("role", "").lower()
    if role not in ("premium", "admin", "administrator"):
        raise HTTPException(
            status_code=403,
            detail="A Premium or Admin account is required to submit entity corrections",
        )
    return user


def _require_admin(user: dict = Depends(require_auth)) -> dict:
    """Only ADMINs may approve or reject corrections."""
    role = user.get("role", "").lower()
    if role not in ("admin", "administrator"):
        raise HTTPException(
            status_code=403,
            detail="Admin privileges required to review entity corrections",
        )
    return user


# ---------------------------------------------------------------------------
# Lazy loaders (keep heavy imports out of module scope)
# ---------------------------------------------------------------------------

def _store():
    from src.knowledge_graph.entity_corrections import get_correction_store
    return get_correction_store()


def _kg_store():
    from src.knowledge_graph.kg_updater import _shared_store
    return _shared_store()


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class CorrectionSubmitRequest(BaseModel):
    correction_type: str = Field(
        ...,
        description=(
            "One of: rename | add_alias | remove_alias | "
            "add_property | remove_property | merge"
        ),
    )
    payload: Dict[str, Any] = Field(
        ...,
        description=(
            "Type-specific data. "
            "rename → {new_name}; "
            "add_alias / remove_alias → {alias}; "
            "add_property → {key, value}; "
            "remove_property → {key}; "
            "merge → {merge_from: entity_id}"
        ),
    )
    reason: str = Field(..., min_length=5, description="Why this correction is needed")


# ---------------------------------------------------------------------------
# User endpoints
# ---------------------------------------------------------------------------

@router.get("/entities/{entity_id}", response_model=Dict[str, Any])
async def get_entity(
    entity_id: str,
    user: dict = Depends(require_auth),
):
    """
    Return the current state of a knowledge-graph entity by its node id.

    The node id has the form ``{type_lower}:{12-char-hex}`` — e.g.
    ``person:4a7f2c9d1b3e``.  Use ``GET /kg/stats`` to see total counts or
    ``GET /kg/topics/evolving`` to find active entity names.
    """
    node = _kg_store().get_node(entity_id)
    if node is None:
        raise HTTPException(
            status_code=404, detail=f"Entity {entity_id!r} not found in the knowledge graph"
        )
    return node.to_dict()


@router.post("/entities/{entity_id}/corrections", response_model=Dict[str, Any], status_code=201)
async def submit_correction(
    entity_id: str,
    body: CorrectionSubmitRequest,
    user: dict = Depends(_require_trusted),
):
    """
    Submit a correction request for an entity.

    The correction is stored as **pending** and visible to admins in the review
    queue.  It is NOT applied to the live knowledge graph until an admin
    approves it via ``POST /admin/entity-corrections/{id}/approve``.

    **Correction types and required payload fields**

    | type            | required payload keys         |
    |-----------------|-------------------------------|
    | rename          | new_name                      |
    | add_alias       | alias                         |
    | remove_alias    | alias                         |
    | add_property    | key, value                    |
    | remove_property | key                           |
    | merge           | merge_from (source entity id) |
    """
    from src.knowledge_graph.entity_corrections import CorrectionType

    # Validate correction_type enum
    try:
        ct = CorrectionType(body.correction_type)
    except ValueError:
        valid = [t.value for t in CorrectionType]
        raise HTTPException(
            status_code=422,
            detail=f"Unknown correction_type {body.correction_type!r}. Valid: {valid}",
        )

    # Ensure target entity exists in the KG (except for merge where source is checked at apply)
    if ct != CorrectionType.MERGE:
        if _kg_store().get_node(entity_id) is None:
            raise HTTPException(
                status_code=404,
                detail=f"Entity {entity_id!r} not found in the knowledge graph",
            )

    try:
        correction = _store().submit(
            entity_id=entity_id,
            correction_type=ct,
            payload=body.payload,
            reason=body.reason,
            submitted_by=user.get("sub", user.get("user_id", "unknown")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return correction.to_dict()


@router.get("/entities/{entity_id}/corrections", response_model=List[Dict[str, Any]])
async def list_entity_corrections(
    entity_id: str,
    status: Optional[str] = Query(None, description="Filter: pending | approved | rejected"),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(require_auth),
):
    """
    List the full correction history for a specific entity, newest first.
    """
    from src.knowledge_graph.entity_corrections import CorrectionStatus

    status_filter = None
    if status is not None:
        try:
            status_filter = CorrectionStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown status {status!r}. Valid: pending, approved, rejected",
            )

    corrections = _store().list_corrections(
        entity_id=entity_id, status=status_filter, limit=limit
    )
    return [c.to_dict() for c in corrections]


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------

@router.get("/admin/entity-corrections", response_model=List[Dict[str, Any]])
async def list_all_corrections(
    status: Optional[str] = Query("pending", description="Filter: pending | approved | rejected | all"),
    entity_id: Optional[str] = Query(None, description="Filter by entity id"),
    limit: int = Query(50, ge=1, le=200),
    admin: dict = Depends(_require_admin),
):
    """
    Admin view of all entity correction requests.

    Defaults to showing only **pending** corrections (the review queue).
    Pass ``status=all`` to see the full history.
    """
    from src.knowledge_graph.entity_corrections import CorrectionStatus

    status_filter: Optional[CorrectionStatus] = None
    if status and status != "all":
        try:
            status_filter = CorrectionStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown status {status!r}. Valid: pending, approved, rejected, all",
            )

    corrections = _store().list_corrections(
        entity_id=entity_id, status=status_filter, limit=limit
    )
    return [c.to_dict() for c in corrections]


@router.get("/admin/entity-corrections/{correction_id}", response_model=Dict[str, Any])
async def get_correction(
    correction_id: str,
    admin: dict = Depends(_require_admin),
):
    """Return full details of a single correction request."""
    correction = _store().get(correction_id)
    if correction is None:
        raise HTTPException(status_code=404, detail=f"Correction {correction_id!r} not found")
    return correction.to_dict()


@router.post("/admin/entity-corrections/{correction_id}/approve", response_model=Dict[str, Any])
async def approve_correction(
    correction_id: str,
    note: Optional[str] = Body(default=None, description="Optional reviewer note"),
    admin: dict = Depends(_require_admin),
):
    """
    Approve a pending correction and immediately apply it to the live
    knowledge graph.

    The admin's user id and the current timestamp are recorded on the
    correction for traceability.
    """
    try:
        correction = _store().approve(
            correction_id=correction_id,
            reviewed_by=admin.get("sub", admin.get("user_id", "unknown")),
            review_note=note,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return correction.to_dict()


@router.post("/admin/entity-corrections/{correction_id}/reject", response_model=Dict[str, Any])
async def reject_correction(
    correction_id: str,
    note: Optional[str] = Body(default=None, description="Optional reviewer note"),
    admin: dict = Depends(_require_admin),
):
    """
    Reject a pending correction.  No knowledge-graph change is made.

    The rejection reason (``note``) is recorded for the submitter to see.
    """
    try:
        correction = _store().reject(
            correction_id=correction_id,
            reviewed_by=admin.get("sub", admin.get("user_id", "unknown")),
            review_note=note,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return correction.to_dict()
