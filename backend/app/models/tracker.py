"""Tracker model representing IoT monitoring hardware."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import String, DateTime, ForeignKey, Enum as SAEnum, UniqueConstraint, func, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.shipment import Shipment
    from app.models.telemetry import Telemetry
    from app.models.alert import Alert


class TrackerStatus(str, enum.Enum):
    """Tracker connection status."""
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"


class Tracker(Base):
    """Cold-chain GPS/sensor tracker assigned to an organization."""

    __tablename__ = "trackers"

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
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    mqtt_topic: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    status: Mapped[TrackerStatus] = mapped_column(
        SAEnum(TrackerStatus, name="tracker_status", native_enum=False),
        default=TrackerStatus.OFFLINE,
        nullable=False,
    )
    last_seen: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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

    # Composite unique constraint enabling multi-tenant foreign keys
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_trackers_id_org"),
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="trackers",
        foreign_keys=[organization_id],
    )
    shipments: Mapped[List["Shipment"]] = relationship(
        "Shipment",
        back_populates="tracker",
        foreign_keys="[Shipment.tracker_id, Shipment.organization_id]",
        overlaps="shipments",
    )
    telemetry: Mapped[List["Telemetry"]] = relationship(
        "Telemetry",
        back_populates="tracker",
        foreign_keys="[Telemetry.tracker_id, Telemetry.organization_id]",
        overlaps="telemetry",
    )
    alerts: Mapped[List["Alert"]] = relationship(
        "Alert",
        back_populates="tracker",
        foreign_keys="[Alert.tracker_id, Alert.organization_id]",
        overlaps="alerts",
    )
