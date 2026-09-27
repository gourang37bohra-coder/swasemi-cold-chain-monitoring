"""Pydantic request/response schemas for authentication endpoints."""

import re
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator

from app.models.user import UserRole

# Standard RFC-compliant pragmatic email regex pattern
EMAIL_REGEX = re.compile(r"^[\w\.\+\-]+@[a-zA-Z0-9\-]+(\.[a-zA-Z0-9\-]+)+$")


# ──────────────────────────────────────────────
# Request Schemas
# ──────────────────────────────────────────────

class RegisterRequest(BaseModel):
    """Payload for POST /auth/register."""

    email: str
    password: str
    organization_id: uuid.UUID

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if not EMAIL_REGEX.match(clean):
            raise ValueError("Invalid email address format.")
        return clean

    @field_validator("password")
    @classmethod
    def password_must_not_be_empty(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v


class LoginRequest(BaseModel):
    """Payload for POST /auth/login."""

    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if not EMAIL_REGEX.match(clean):
            raise ValueError("Invalid email address format.")
        return clean


# ──────────────────────────────────────────────
# Response Schemas
# ──────────────────────────────────────────────

class TokenResponse(BaseModel):
    """JWT token response returned after successful login."""

    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Safe user representation — never includes password_hash."""

    id: uuid.UUID
    email: str
    organization_id: Optional[uuid.UUID]
    role: UserRole
    created_at: datetime

    model_config = {"from_attributes": True}
