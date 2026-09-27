"""Shipment model tracking cold-chain goods and temperature profiles."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import (
    Float,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    Enum as SAEnum,
    UniqueConstraint,
    ForeignKeyConstraint,
    func,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.tracker import Tracker
    from app.models.telemetry import Telemetry
    from app.models.alert import Alert


class ShipmentStatus(str, enum.Enum):
    """Lifecycle status of a shipment."""
    NOT_STARTED = "NOT_STARTED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"


class Shipment(Base):
    """Shipment entity with temperature tolerance profile and lifecycle timestamps."""

    __tablename__ = "shipments"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    tracker_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
        index=True,
    )
    status: Mapped[ShipmentStatus] = mapped_column(
        SAEnum(ShipmentStatus, name="shipment_status", native_enum=False),
        default=ShipmentStatus.NOT_STARTED,
        nullable=False,
        index=True,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    minimum_temperature: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    maximum_temperature: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    grace_readings: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    consecutive_violations: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    breach_active: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Multi-tenant constraints: composite unique and composite foreign key
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_shipments_id_org"),
        ForeignKeyConstraint(
            ["tracker_id", "organization_id"],
            ["trackers.id", "trackers.organization_id"],
            ondelete="RESTRICT",
            name="fk_shipments_tracker_org",
        ),
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="shipments",
        foreign_keys=[organization_id],
        overlaps="tracker,shipments",
    )
    tracker: Mapped["Tracker"] = relationship(
        "Tracker",
        back_populates="shipments",
        foreign_keys=[tracker_id, organization_id],
        overlaps="organization,shipments",
    )
    telemetry: Mapped[List["Telemetry"]] = relationship(
        "Telemetry",
        back_populates="shipment",
        foreign_keys="[Telemetry.shipment_id, Telemetry.organization_id]",
        overlaps="telemetry,tracker,organization",
    )
    alerts: Mapped[List["Alert"]] = relationship(
        "Alert",
        back_populates="shipment",
        foreign_keys="[Alert.shipment_id, Alert.organization_id]",
        overlaps="alerts,tracker,organization",
    )
