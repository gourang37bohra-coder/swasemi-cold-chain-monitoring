"""Tracker management API router: CRUD operations with multi-tenant isolation."""

import logging
from typing import Annotated, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth_deps import TenantContext, get_tenant_context
from app.core.database import get_db
from app.models.organization import Organization
from app.models.tracker import Tracker
from app.schemas.tracker import (
    PaginatedTrackersResponse,
    TrackerCreate,
    TrackerResponse,
    TrackerUpdate,
)

logger = logging.getLogger("coldchain.trackers")
router = APIRouter(prefix="/trackers", tags=["Trackers"])


# ──────────────────────────────────────────────
# POST /trackers
# ──────────────────────────────────────────────

@router.post(
    "",
    response_model=TrackerResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_tracker(
    payload: TrackerCreate,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> Tracker:
    """Create a new tracker.

    - USER: Assigned strictly to the user's organization. Any organization_id
      in payload is ignored.
    - SUPER_ADMIN: Can assign to any organization. organization_id is required.
    """
    if tenant_context.is_super_admin:
        if payload.organization_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="organization_id is required when creating a tracker as SUPER_ADMIN.",
            )
        target_org_id = payload.organization_id
    else:
        target_org_id = tenant_context.organization_id

    # Verify target organization exists
    org = db.scalar(select(Organization).where(Organization.id == target_org_id))
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Target organization not found.",
        )

    tracker = Tracker(
        organization_id=target_org_id,
        name=payload.name,
        mqtt_topic=payload.mqtt_topic,
        status=payload.status,
    )
    db.add(tracker)
    db.commit()
    db.refresh(tracker)
    return tracker


# ──────────────────────────────────────────────
# GET /trackers
# ──────────────────────────────────────────────

@router.get(
    "",
    response_model=PaginatedTrackersResponse,
)
def list_trackers(
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    organization_id: Optional[uuid.UUID] = Query(
        None, description="Filter by organization (SUPER_ADMIN only)"
    ),
) -> PaginatedTrackersResponse:
    """List trackers with tenant isolation and pagination.

    - USER: Only sees trackers for their own organization.
    - SUPER_ADMIN: Sees all trackers, or filtered by optional organization_id.
    """
    base_query = select(Tracker)

    if tenant_context.is_super_admin:
        if organization_id is not None:
            base_query = base_query.where(Tracker.organization_id == organization_id)
    else:
        # Enforce strict organization boundary in PostgreSQL
        base_query = base_query.where(
            Tracker.organization_id == tenant_context.organization_id
        )

    # Compute total count
    count_query = select(func.count()).select_from(base_query.subquery())
    total = db.scalar(count_query) or 0

    # Paginate and fetch
    offset = (page - 1) * page_size
    items_query = (
        base_query.order_by(Tracker.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    items = list(db.scalars(items_query).all())

    return PaginatedTrackersResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
    )


# ──────────────────────────────────────────────
# GET /trackers/{tracker_id}
# ──────────────────────────────────────────────

@router.get(
    "/{tracker_id}",
    response_model=TrackerResponse,
)
def get_tracker(
    tracker_id: uuid.UUID,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> Tracker:
    """Retrieve details of a single tracker.

    Zero-knowledge 404 is returned if the tracker does not exist or belongs
    to another organization for a normal USER.
    """
    query = select(Tracker).where(Tracker.id == tracker_id)
    if not tenant_context.is_super_admin:
        query = query.where(Tracker.organization_id == tenant_context.organization_id)

    tracker = db.scalar(query)
    if tracker is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tracker not found.",
        )
    return tracker


# ──────────────────────────────────────────────
# PATCH /trackers/{tracker_id}
# ──────────────────────────────────────────────

@router.patch(
    "/{tracker_id}",
    response_model=TrackerResponse,
)
def update_tracker(
    tracker_id: uuid.UUID,
    payload: TrackerUpdate,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> Tracker:
    """Update tracker mutable fields (name, mqtt_topic, status)."""
    query = select(Tracker).where(Tracker.id == tracker_id)
    if not tenant_context.is_super_admin:
        query = query.where(Tracker.organization_id == tenant_context.organization_id)

    tracker = db.scalar(query)
    if tracker is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tracker not found.",
        )

    if payload.name is not None:
        tracker.name = payload.name
    if payload.mqtt_topic is not None:
        tracker.mqtt_topic = payload.mqtt_topic
    if payload.status is not None:
        tracker.status = payload.status

    db.commit()
    db.refresh(tracker)
    return tracker


# ──────────────────────────────────────────────
# DELETE /trackers/{tracker_id}
# ──────────────────────────────────────────────

@router.delete(
    "/{tracker_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_tracker(
    tracker_id: uuid.UUID,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> None:
    """Delete a tracker.

    Enforces RESTRICT constraints at the database level: if any shipments
    or telemetry are associated with this tracker, returns HTTP 409 Conflict.
    """
    query = select(Tracker).where(Tracker.id == tracker_id)
    if not tenant_context.is_super_admin:
        query = query.where(Tracker.organization_id == tenant_context.organization_id)

    tracker = db.scalar(query)
    if tracker is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tracker not found.",
        )

    try:
        db.delete(tracker)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete tracker with associated shipments or telemetry records.",
        )
