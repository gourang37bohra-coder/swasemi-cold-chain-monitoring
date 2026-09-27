"""Pydantic schemas for Super Admin user provisioning endpoints."""

from datetime import datetime
from typing import List, Optional
import uuid

from pydantic import BaseModel, Field, field_validator

from app.models.user import UserRole
from app.schemas.auth import EMAIL_REGEX


class AdminUserCreate(BaseModel):
    """Payload for administrative user provisioning."""

    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=8, description="Initial password (min 8 characters)")
    role: UserRole = Field(default=UserRole.USER, description="User role (USER or SUPER_ADMIN)")
    organization_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Target organization UUID. Required for USER role; must be null for SUPER_ADMIN.",
    )

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if not EMAIL_REGEX.match(clean):
            raise ValueError("Invalid email address format.")
        return clean

    @field_validator("password")
    @classmethod
    def validate_password_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v


class AdminUserUpdate(BaseModel):
    """Payload for modifying user account properties."""

    password: Optional[str] = Field(default=None, min_length=8, description="New password (min 8 characters)")
    role: Optional[UserRole] = Field(default=None, description="Updated role")
    organization_id: Optional[uuid.UUID] = Field(default=None, description="Updated organization")

    @field_validator("password")
    @classmethod
    def validate_new_password_length(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v


class AdminUserResponse(BaseModel):
    """Safe public user representation (never includes password_hash)."""

    id: uuid.UUID
    email: str
    role: UserRole
    organization_id: Optional[uuid.UUID]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PaginatedAdminUsersResponse(BaseModel):
    """Paginated list of user accounts."""

    items: List[AdminUserResponse]
    page: int
    page_size: int
    total: int
