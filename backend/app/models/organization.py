"""Organization model representing client tenants."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List
from sqlalchemy import String, DateTime, func, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.tracker import Tracker
    from app.models.shipment import Shipment
    from app.models.telemetry import Telemetry
    from app.models.alert import Alert


class Organization(Base):
    """Organization (tenant) entity that isolates client data across the platform."""

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
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

    # Relationships
    users: Mapped[List["User"]] = relationship(
        "User",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    trackers: Mapped[List["Tracker"]] = relationship(
        "Tracker",
        back_populates="organization",
    )
    shipments: Mapped[List["Shipment"]] = relationship(
        "Shipment",
        back_populates="organization",
    )
    telemetry: Mapped[List["Telemetry"]] = relationship(
        "Telemetry",
        back_populates="organization",
    )
    alerts: Mapped[List["Alert"]] = relationship(
        "Alert",
        back_populates="organization",
    )
