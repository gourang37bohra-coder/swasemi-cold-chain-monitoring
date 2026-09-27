"""Pydantic schemas for Tracker management endpoints."""

from datetime import datetime
from typing import List, Optional
import uuid

from pydantic import BaseModel, Field

from app.models.tracker import TrackerStatus


class TrackerCreate(BaseModel):
    """Payload for creating a new tracker."""

    name: str = Field(..., min_length=1, max_length=255, description="Tracker display name")
    mqtt_topic: str = Field(..., min_length=1, max_length=255, description="MQTT topic for telemetry ingestion")
    status: TrackerStatus = Field(default=TrackerStatus.OFFLINE, description="Initial tracker status")
    organization_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Target organization UUID. Required for SUPER_ADMIN; ignored/overridden for USER.",
    )


class TrackerUpdate(BaseModel):
    """Payload for modifying an existing tracker."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    mqtt_topic: Optional[str] = Field(default=None, min_length=1, max_length=255)
    status: Optional[TrackerStatus] = Field(default=None)


class TrackerResponse(BaseModel):
    """Public representation of a tracker."""

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    mqtt_topic: str
    status: TrackerStatus
    last_seen: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PaginatedTrackersResponse(BaseModel):
    """Paginated list of trackers."""

    items: List[TrackerResponse]
    page: int
    page_size: int
    total: int
