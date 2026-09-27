"""Alerts query API router: tenant-isolated alert retrieval with pagination."""

from datetime import datetime
import logging
from typing import Annotated, Optional
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth_deps import TenantContext, get_tenant_context
from app.core.database import get_db
from app.models.alert import Alert, AlertType
from app.schemas.alert import PaginatedAlertsResponse

logger = logging.getLogger("coldchain.alerts.api")
router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.get(
    "",
    response_model=PaginatedAlertsResponse,
    summary="List tenant alerts with pagination and optional filters",
)
def list_alerts(
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    shipment_id: Optional[uuid.UUID] = Query(None, description="Filter by shipment ID"),
    tracker_id: Optional[uuid.UUID] = Query(None, description="Filter by tracker ID"),
    alert_type: Optional[AlertType] = Query(None, description="Filter by alert type"),
    organization_id: Optional[uuid.UUID] = Query(
        None, description="Filter by organization (SUPER_ADMIN only)"
    ),
) -> PaginatedAlertsResponse:
    """Retrieve breach alerts with strict tenant scoping.

    - USER: Strictly confined to their organization.
    - SUPER_ADMIN: Can query across all organizations or filter by specific organization_id.
    """
    base_query = select(Alert)

    if tenant_context.is_super_admin:
        if organization_id is not None:
            base_query = base_query.where(Alert.organization_id == organization_id)
    else:
        base_query = base_query.where(
            Alert.organization_id == tenant_context.organization_id
        )

    if shipment_id is not None:
        base_query = base_query.where(Alert.shipment_id == shipment_id)
    if tracker_id is not None:
        base_query = base_query.where(Alert.tracker_id == tracker_id)
    if alert_type is not None:
        base_query = base_query.where(Alert.type == alert_type)

    total_query = select(func.count()).select_from(base_query.subquery())
    total = db.scalar(total_query) or 0

    offset = (page - 1) * page_size
    items_query = (
        base_query.order_by(Alert.triggered_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    items = list(db.scalars(items_query).all())

    return PaginatedAlertsResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
    )
