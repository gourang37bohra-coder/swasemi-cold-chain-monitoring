"""Pydantic schemas for telemetry ingestion and querying."""

from datetime import datetime
from typing import List, Optional
import uuid

from pydantic import BaseModel, Field


class TelemetryPayload(BaseModel):
    """Schema for validating raw MQTT telemetry messages."""

    tracker_id: uuid.UUID = Field(..., description="UUID of the emitting tracker")
    timestamp: datetime = Field(..., description="UTC timestamp of the sensor reading")
    temperature: float = Field(..., description="Recorded temperature in Celsius")
    latitude: float = Field(..., ge=-90.0, le=90.0, description="GPS Latitude (-90 to 90)")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="GPS Longitude (-180 to 180)")
    humidity: float = Field(default=50.0, ge=0.0, le=100.0, description="Relative humidity percentage")
    battery: float = Field(default=100.0, ge=0.0, le=100.0, description="Battery level percentage")
    door_status: bool = Field(default=False, description="Refrigeration door open status (True=open)")


class TelemetryResponse(BaseModel):
    """Public representation of a persisted telemetry record."""

    id: uuid.UUID
    organization_id: uuid.UUID
    shipment_id: uuid.UUID
    tracker_id: uuid.UUID
    temperature: float
    humidity: float
    battery: float
    door_status: bool
    latitude: float
    longitude: float
    timestamp: datetime

    model_config = {"from_attributes": True}


class PaginatedTelemetryResponse(BaseModel):
    """Paginated list of telemetry records."""

    items: List[TelemetryResponse]
    page: int
    page_size: int
    total: int
