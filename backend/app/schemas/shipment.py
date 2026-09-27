"""Pydantic schemas for Shipment management and lifecycle endpoints."""

from datetime import datetime
from typing import List, Optional
import uuid

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.shipment import ShipmentStatus


class ShipmentCreate(BaseModel):
    """Payload for creating a new cold-chain shipment."""

    tracker_id: uuid.UUID = Field(..., description="UUID of the assigned tracker")
    minimum_temperature: float = Field(..., description="Minimum allowed temperature in Celsius")
    maximum_temperature: float = Field(..., description="Maximum allowed temperature in Celsius")
    grace_readings: int = Field(default=1, ge=1, description="Readings allowed outside range before breach")
    organization_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Target organization UUID. Allowed for SUPER_ADMIN; overridden for USER.",
    )

    @field_validator("grace_readings")
    @classmethod
    def validate_grace_readings(cls, v: int) -> int:
        if v < 1:
            raise ValueError("grace_readings must be at least 1.")
        return v

    @model_validator(mode="after")
    def validate_temperature_range(self) -> "ShipmentCreate":
        if self.minimum_temperature >= self.maximum_temperature:
            raise ValueError(
                f"minimum_temperature ({self.minimum_temperature}) must be strictly less than "
                f"maximum_temperature ({self.maximum_temperature})."
            )
        return self


class ShipmentResponse(BaseModel):
    """Public representation of a shipment with lifecycle state."""

    id: uuid.UUID
    organization_id: uuid.UUID
    tracker_id: uuid.UUID
    status: ShipmentStatus
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    minimum_temperature: float
    maximum_temperature: float
    grace_readings: int
    consecutive_violations: int = 0
    breach_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PaginatedShipmentsResponse(BaseModel):
    """Paginated list of shipments."""

    items: List[ShipmentResponse]
    page: int
    page_size: int
    total: int


class ShipmentMetrics(BaseModel):
    """Aggregated statistical and duration metrics for historical shipment inspection."""

    reading_count: int
    latest_temperature: Optional[float] = None
    min_temperature: Optional[float] = None
    max_temperature: Optional[float] = None
    avg_temperature: Optional[float] = None
    duration_seconds: Optional[float] = None


class ShipmentHistoryResponse(BaseModel):
    """Comprehensive historical detail response including telemetry and aggregated metrics."""

    shipment: ShipmentResponse
    metrics: ShipmentMetrics

