"""Pydantic schemas for Organization management endpoints."""

from datetime import datetime
from typing import List, Optional
import uuid

from pydantic import BaseModel, Field


class OrganizationCreate(BaseModel):
    """Payload for creating a new organization."""

    name: str = Field(..., min_length=1, max_length=255, description="Organization display name")


class OrganizationUpdate(BaseModel):
    """Payload for updating an organization."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=255, description="Updated name")


class OrganizationResponse(BaseModel):
    """Safe public representation of an organization."""

    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime
    user_count: Optional[int] = Field(default=0, description="Number of users in this organization")

    model_config = {"from_attributes": True}


class PaginatedOrganizationsResponse(BaseModel):
    """Paginated list of organizations."""

    items: List[OrganizationResponse]
    page: int
    page_size: int
    total: int
