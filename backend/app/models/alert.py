"""Alert model for temperature breaches and shipment warnings."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import (
    Float,
    Text,
    DateTime,
    ForeignKey,
    Enum as SAEnum,
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


class AlertType(str, enum.Enum):
    """Types of alerts triggered during shipments."""
    TEMPERATURE_BREACH = "TEMPERATURE_BREACH"
    DOOR_OPEN = "DOOR_OPEN"
    LOW_BATTERY = "LOW_BATTERY"


class Alert(Base):
    """Alert record logged for a shipment/tracker violation."""

    __tablename__ = "alerts"

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
    type: Mapped[AlertType] = mapped_column(
        SAEnum(AlertType, name="alert_type", native_enum=False),
        nullable=False,
        index=True,
    )
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    temperature: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Multi-tenant composite foreign keys and composite indexes
    __table_args__ = (
        ForeignKeyConstraint(
            ["tracker_id", "organization_id"],
            ["trackers.id", "trackers.organization_id"],
            ondelete="RESTRICT",
            name="fk_alerts_tracker_org",
        ),
        ForeignKeyConstraint(
            ["shipment_id", "organization_id"],
            ["shipments.id", "shipments.organization_id"],
            ondelete="RESTRICT",
            name="fk_alerts_shipment_org",
        ),
        Index("ix_alerts_shipment_triggered", "shipment_id", "triggered_at"),
        Index("ix_alerts_org_triggered", "organization_id", "triggered_at"),
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="alerts",
        foreign_keys=[organization_id],
        overlaps="alerts,tracker,shipment",
    )
    shipment: Mapped["Shipment"] = relationship(
        "Shipment",
        back_populates="alerts",
        foreign_keys=[shipment_id, organization_id],
        overlaps="alerts,organization,tracker",
    )
    tracker: Mapped["Tracker"] = relationship(
        "Tracker",
        back_populates="alerts",
        foreign_keys=[tracker_id, organization_id],
        overlaps="alerts,organization,shipment",
    )
