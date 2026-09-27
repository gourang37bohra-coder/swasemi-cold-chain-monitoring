"""Telemetry model for time-series sensor and GPS readings."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import (
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    ForeignKeyConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.shipment import Shipment
    from app.models.tracker import Tracker


class Telemetry(Base):
    """Telemetry readings emitted by trackers and persisted during active shipments."""

    __tablename__ = "telemetry"

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
    shipment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
        index=True,
    )
    tracker_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
        index=True,
    )
    temperature: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    humidity: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    battery: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    door_status: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )
    latitude: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    longitude: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    # Multi-tenant composite foreign keys and time-series composite indexes
    __table_args__ = (
        ForeignKeyConstraint(
            ["tracker_id", "organization_id"],
            ["trackers.id", "trackers.organization_id"],
            ondelete="RESTRICT",
            name="fk_telemetry_tracker_org",
        ),
        ForeignKeyConstraint(
            ["shipment_id", "organization_id"],
            ["shipments.id", "shipments.organization_id"],
            ondelete="RESTRICT",
            name="fk_telemetry_shipment_org",
        ),
        Index("ix_telemetry_shipment_timestamp", "shipment_id", "timestamp"),
        Index("ix_telemetry_tracker_timestamp", "tracker_id", "timestamp"),
        Index("ix_telemetry_org_timestamp", "organization_id", "timestamp"),
        Index("ix_telemetry_org_shipment_timestamp", "organization_id", "shipment_id", "timestamp"),
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="telemetry",
        foreign_keys=[organization_id],
        overlaps="telemetry,tracker,shipment",
    )
    shipment: Mapped["Shipment"] = relationship(
        "Shipment",
        back_populates="telemetry",
        foreign_keys=[shipment_id, organization_id],
        overlaps="telemetry,organization,tracker",
    )
    tracker: Mapped["Tracker"] = relationship(
        "Tracker",
        back_populates="telemetry",
        foreign_keys=[tracker_id, organization_id],
        overlaps="telemetry,organization,shipment",
    )
