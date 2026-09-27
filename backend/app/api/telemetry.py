"""Telemetry query API router: tenant-isolated sensor data retrieval with filters."""

from datetime import datetime
import logging
from typing import Annotated, Optional
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth_deps import TenantContext, get_tenant_context
from app.core.database import get_db
from app.models.telemetry import Telemetry
from app.schemas.telemetry import PaginatedTelemetryResponse

logger = logging.getLogger("coldchain.telemetry.api")
router = APIRouter(prefix="/telemetry", tags=["Telemetry"])


# ──────────────────────────────────────────────
# GET /telemetry
# ──────────────────────────────────────────────

@router.get(
    "",
    response_model=PaginatedTelemetryResponse,
)
def list_telemetry(
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    tracker_id: Optional[uuid.UUID] = Query(None, description="Filter by tracker ID"),
    shipment_id: Optional[uuid.UUID] = Query(None, description="Filter by shipment ID"),
    start_time: Optional[datetime] = Query(None, description="Filter by start timestamp (inclusive)"),
    end_time: Optional[datetime] = Query(None, description="Filter by end timestamp (inclusive)"),
    organization_id: Optional[uuid.UUID] = Query(
        None, description="Filter by organization (SUPER_ADMIN only)"
    ),
) -> PaginatedTelemetryResponse:
    """Retrieve historical telemetry with tenant isolation, filters, and pagination.

    - USER: Only queries telemetry within their assigned organization.
    - SUPER_ADMIN: Can query across organizations or filter by specific organization_id.
    """
    base_query = select(Telemetry)

    # Tenant scoping directly in PostgreSQL
    if tenant_context.is_super_admin:
        if organization_id is not None:
            base_query = base_query.where(Telemetry.organization_id == organization_id)
    else:
        base_query = base_query.where(
            Telemetry.organization_id == tenant_context.organization_id
        )

    # Optional filters
    if tracker_id is not None:
        base_query = base_query.where(Telemetry.tracker_id == tracker_id)
    if shipment_id is not None:
        base_query = base_query.where(Telemetry.shipment_id == shipment_id)
    if start_time is not None:
        base_query = base_query.where(Telemetry.timestamp >= start_time)
    if end_time is not None:
        base_query = base_query.where(Telemetry.timestamp <= end_time)

    # Total count query executed in PostgreSQL
    count_query = select(func.count()).select_from(base_query.subquery())
    total = db.scalar(count_query) or 0

    # Paginated results ordered by timestamp descending
    offset = (page - 1) * page_size
    items_query = (
        base_query.order_by(Telemetry.timestamp.desc())
        .offset(offset)
        .limit(page_size)
    )
    items = list(db.scalars(items_query).all())

    return PaginatedTelemetryResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
    )
