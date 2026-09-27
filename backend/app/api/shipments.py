import csv
from datetime import datetime, timezone
import io
import logging
from typing import Annotated, Generator, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth_deps import TenantContext, get_tenant_context
from app.core.database import get_db
from app.models.alert import Alert
from app.models.shipment import Shipment, ShipmentStatus
from app.models.telemetry import Telemetry
from app.models.tracker import Tracker
from app.schemas.alert import AlertResponse
from app.schemas.shipment import (
    PaginatedShipmentsResponse,
    ShipmentCreate,
    ShipmentHistoryResponse,
    ShipmentMetrics,
    ShipmentResponse,
)
from app.schemas.telemetry import TelemetryResponse

logger = logging.getLogger("coldchain.shipments")
router = APIRouter(prefix="/shipments", tags=["Shipments"])


# ──────────────────────────────────────────────
# POST /shipments
# ──────────────────────────────────────────────

@router.post(
    "",
    response_model=ShipmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_shipment(
    payload: ShipmentCreate,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> Shipment:
    """Create a new cold-chain shipment.

    Enforces that:
      1. Target organization is resolved from user context (USER) or payload/tracker (SUPER_ADMIN).
      2. The assigned tracker exists within that target organization.
      3. Temperature boundaries and grace reading constraints are validated.
      4. Initial lifecycle state is set to NOT_STARTED.
    """
    if tenant_context.is_super_admin:
        if payload.organization_id is not None:
            target_org_id = payload.organization_id
        else:
            # Infer organization from the tracker
            tracker_check = db.scalar(
                select(Tracker).where(Tracker.id == payload.tracker_id)
            )
            if tracker_check is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Tracker not found.",
                )
            target_org_id = tracker_check.organization_id
    else:
        target_org_id = tenant_context.organization_id

    # Tenant-scoping check: tracker must belong to the resolved organization
    tracker = db.scalar(
        select(Tracker).where(
            Tracker.id == payload.tracker_id,
            Tracker.organization_id == target_org_id,
        )
    )
    if tracker is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tracker not found.",
        )

    shipment = Shipment(
        organization_id=target_org_id,
        tracker_id=payload.tracker_id,
        status=ShipmentStatus.NOT_STARTED,
        started_at=None,
        ended_at=None,
        minimum_temperature=payload.minimum_temperature,
        maximum_temperature=payload.maximum_temperature,
        grace_readings=payload.grace_readings,
        breach_active=False,
    )
    db.add(shipment)
    db.commit()
    db.refresh(shipment)
    return shipment


# ──────────────────────────────────────────────
# GET /shipments
# ──────────────────────────────────────────────

@router.get(
    "",
    response_model=PaginatedShipmentsResponse,
)
def list_shipments(
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    organization_id: Optional[uuid.UUID] = Query(
        None, description="Filter by organization (SUPER_ADMIN only)"
    ),
) -> PaginatedShipmentsResponse:
    """List shipments with tenant isolation and pagination."""
    base_query = select(Shipment)

    if tenant_context.is_super_admin:
        if organization_id is not None:
            base_query = base_query.where(Shipment.organization_id == organization_id)
    else:
        base_query = base_query.where(
            Shipment.organization_id == tenant_context.organization_id
        )

    # Compute total count directly in PostgreSQL
    count_query = select(func.count()).select_from(base_query.subquery())
    total = db.scalar(count_query) or 0

    # Paginate
    offset = (page - 1) * page_size
    items_query = (
        base_query.order_by(Shipment.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    items = list(db.scalars(items_query).all())

    return PaginatedShipmentsResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
    )


# ──────────────────────────────────────────────
# GET /shipments/{shipment_id}
# ──────────────────────────────────────────────

@router.get(
    "/{shipment_id}",
    response_model=ShipmentResponse,
)
def get_shipment(
    shipment_id: uuid.UUID,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> Shipment:
    """Retrieve details of a single shipment.

    Returns zero-knowledge 404 if shipment belongs to another organization.
    """
    query = select(Shipment).where(Shipment.id == shipment_id)
    if not tenant_context.is_super_admin:
        query = query.where(Shipment.organization_id == tenant_context.organization_id)

    shipment = db.scalar(query)
    if shipment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shipment not found.",
        )
    return shipment


# ──────────────────────────────────────────────
# POST /shipments/{shipment_id}/start
# ──────────────────────────────────────────────

@router.post(
    "/{shipment_id}/start",
    response_model=ShipmentResponse,
)
def start_shipment(
    shipment_id: uuid.UUID,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> Shipment:
    """Transition shipment lifecycle: NOT_STARTED -> ACTIVE.

    - Sets started_at to current UTC timestamp.
    - Rejects transitions if current status is not NOT_STARTED (HTTP 409).
    """
    query = select(Shipment).where(Shipment.id == shipment_id)
    if not tenant_context.is_super_admin:
        query = query.where(Shipment.organization_id == tenant_context.organization_id)

    shipment = db.scalar(query)
    if shipment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shipment not found.",
        )

    if shipment.status != ShipmentStatus.NOT_STARTED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot start shipment with status {shipment.status.value}. "
                "Only NOT_STARTED shipments can be started."
            ),
        )

    shipment.status = ShipmentStatus.ACTIVE
    shipment.started_at = datetime.now(timezone.utc)
    shipment.ended_at = None
    shipment.breach_active = False

    db.commit()
    db.refresh(shipment)
    return shipment


# ──────────────────────────────────────────────
# POST /shipments/{shipment_id}/complete
# ──────────────────────────────────────────────

@router.post(
    "/{shipment_id}/complete",
    response_model=ShipmentResponse,
)
def complete_shipment(
    shipment_id: uuid.UUID,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> Shipment:
    """Transition shipment lifecycle: ACTIVE -> COMPLETED.

    - Sets ended_at to current UTC timestamp.
    - Rejects transitions if current status is not ACTIVE (HTTP 409).
    """
    query = select(Shipment).where(Shipment.id == shipment_id)
    if not tenant_context.is_super_admin:
        query = query.where(Shipment.organization_id == tenant_context.organization_id)

    shipment = db.scalar(query)
    if shipment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shipment not found.",
        )

    if shipment.status != ShipmentStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot complete shipment with status {shipment.status.value}. "
                "Only ACTIVE shipments can be completed."
            ),
        )

    shipment.status = ShipmentStatus.COMPLETED
    shipment.ended_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(shipment)
    return shipment


# ──────────────────────────────────────────────
# GET /shipments/{shipment_id}/history
# ──────────────────────────────────────────────

@router.get(
    "/{shipment_id}/history",
    response_model=ShipmentHistoryResponse,
    summary="Get shipment details with computed metrics",
)
def get_shipment_history(
    shipment_id: uuid.UUID,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> ShipmentHistoryResponse:
    """Retrieve comprehensive historical detail and aggregated metrics for a shipment.

    Tenant isolation:
      - USER: Strictly confined to own organization_id.
      - SUPER_ADMIN: Can inspect shipments across all organizations.
    """
    query = select(Shipment).where(Shipment.id == shipment_id)
    if not tenant_context.is_super_admin:
        query = query.where(Shipment.organization_id == tenant_context.organization_id)

    shipment = db.scalar(query)
    if shipment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shipment not found.",
        )

    # Aggregated metrics directly in PostgreSQL
    agg_query = select(
        func.count(Telemetry.id),
        func.min(Telemetry.temperature),
        func.max(Telemetry.temperature),
        func.avg(Telemetry.temperature),
    ).where(Telemetry.shipment_id == shipment.id)
    count, min_temp, max_temp, avg_temp = db.execute(agg_query).one()

    # Latest reading
    latest_reading = db.scalar(
        select(Telemetry)
        .where(Telemetry.shipment_id == shipment.id)
        .order_by(Telemetry.timestamp.desc())
        .limit(1)
    )

    # Duration in seconds
    duration_seconds: Optional[float] = None
    if shipment.started_at is not None:
        end_time = shipment.ended_at or (latest_reading.timestamp if latest_reading else datetime.now(timezone.utc))
        duration_seconds = max(0.0, (end_time - shipment.started_at).total_seconds())

    metrics = ShipmentMetrics(
        reading_count=count or 0,
        latest_temperature=float(latest_reading.temperature) if latest_reading else None,
        min_temperature=float(min_temp) if min_temp is not None else None,
        max_temperature=float(max_temp) if max_temp is not None else None,
        avg_temperature=round(float(avg_temp), 2) if avg_temp is not None else None,
        duration_seconds=duration_seconds,
    )

    return ShipmentHistoryResponse(
        shipment=shipment,
        metrics=metrics,
    )


# ──────────────────────────────────────────────
# GET /shipments/{shipment_id}/telemetry
# ──────────────────────────────────────────────

@router.get(
    "/{shipment_id}/telemetry",
    response_model=List[TelemetryResponse],
    summary="Get all telemetry records for a shipment in chronological order",
)
def get_shipment_telemetry(
    shipment_id: uuid.UUID,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> List[Telemetry]:
    """Retrieve full chronological telemetry readings belonging exclusively to this shipment."""
    query = select(Shipment).where(Shipment.id == shipment_id)
    if not tenant_context.is_super_admin:
        query = query.where(Shipment.organization_id == tenant_context.organization_id)

    shipment = db.scalar(query)
    if shipment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shipment not found.",
        )

    records = list(
        db.scalars(
            select(Telemetry)
            .where(Telemetry.shipment_id == shipment.id)
            .order_by(Telemetry.timestamp.asc())
        ).all()
    )
    return records


# ──────────────────────────────────────────────
# GET /shipments/{shipment_id}/export.csv
# ──────────────────────────────────────────────

@router.get(
    "/{shipment_id}/export.csv",
    summary="Export shipment telemetry as downloadable CSV",
)
def export_shipment_csv(
    shipment_id: uuid.UUID,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Stream all telemetry records for a shipment as a formatted CSV attachment.

    Guarantees:
      - Strictly tenant-authorized (USER cannot download another org's data).
      - Streamed row-by-row to optimize memory consumption.
      - Uses Content-Disposition: attachment; filename="shipment_{id}_telemetry.csv".
    """
    query = select(Shipment).where(Shipment.id == shipment_id)
    if not tenant_context.is_super_admin:
        query = query.where(Shipment.organization_id == tenant_context.organization_id)

    shipment = db.scalar(query)
    if shipment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shipment not found.",
        )

    records = list(
        db.scalars(
            select(Telemetry)
            .where(Telemetry.shipment_id == shipment.id)
            .order_by(Telemetry.timestamp.asc())
        ).all()
    )

    def iter_csv() -> Generator[str, None, None]:
        output = io.StringIO()
        writer = csv.writer(output)
        # Header row
        writer.writerow([
            "timestamp",
            "tracker_id",
            "shipment_id",
            "temperature",
            "humidity",
            "battery",
            "door_status",
            "latitude",
            "longitude",
        ])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        for record in records:
            writer.writerow([
                record.timestamp.isoformat(),
                str(record.tracker_id),
                str(record.shipment_id),
                f"{record.temperature:.2f}",
                f"{record.humidity:.1f}",
                f"{record.battery:.1f}",
                "open" if record.door_status else "closed",
                f"{record.latitude:.6f}",
                f"{record.longitude:.6f}",
            ])
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    filename = f"shipment_{shipment.id}_telemetry.csv"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": "text/csv; charset=utf-8",
    }
    return StreamingResponse(iter_csv(), media_type="text/csv", headers=headers)


# ──────────────────────────────────────────────
# GET /shipments/{shipment_id}/alerts
# ──────────────────────────────────────────────

@router.get(
    "/{shipment_id}/alerts",
    response_model=List[AlertResponse],
    summary="Get all alerts for a shipment",
)
def get_shipment_alerts(
    shipment_id: uuid.UUID,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Session = Depends(get_db),
) -> List[Alert]:
    """Retrieve all breach alerts triggered for this shipment."""
    query = select(Shipment).where(Shipment.id == shipment_id)
    if not tenant_context.is_super_admin:
        query = query.where(Shipment.organization_id == tenant_context.organization_id)

    shipment = db.scalar(query)
    if shipment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shipment not found.",
        )

    alerts = list(
        db.scalars(
            select(Alert)
            .where(Alert.shipment_id == shipment.id)
            .order_by(Alert.triggered_at.desc())
        ).all()
    )
    return alerts

