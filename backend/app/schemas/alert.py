"""Pydantic schemas for Alert records and notifications."""

from datetime import datetime
from typing import List, Optional
import uuid

from pydantic import BaseModel, Field

from app.models.alert import AlertType


class AlertResponse(BaseModel):
    """Public representation of an alert record."""

    id: uuid.UUID
    organization_id: uuid.UUID
    shipment_id: uuid.UUID
    tracker_id: uuid.UUID
    type: AlertType
    message: str
    temperature: Optional[float] = None
    triggered_at: datetime
    resolved_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PaginatedAlertsResponse(BaseModel):
    """Paginated response containing Alert items."""

    items: List[AlertResponse]
    page: int
    page_size: int
    total: int
