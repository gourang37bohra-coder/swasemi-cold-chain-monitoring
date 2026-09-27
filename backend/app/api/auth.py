"""Authentication API router: registration, login, and current-user endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth_deps import get_current_user
from app.core.database import get_db
from app.core.security import create_access_token, verify_password
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse, UserResponse

logger = logging.getLogger("coldchain.auth")
router = APIRouter(prefix="/auth", tags=["Authentication"])


# ──────────────────────────────────────────────
# POST /auth/login
# ──────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Authenticate a user and return a signed JWT.

    Uses a generic error message for both unknown email and wrong password
    to avoid user-enumeration attacks.
    """
    _INVALID = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise _INVALID

    token = create_access_token(
        user_id=user.id,
        org_id=user.organization_id,
        role=user.role.value,
    )
    return TokenResponse(access_token=token, token_type="bearer")


# ──────────────────────────────────────────────
# GET /auth/me
# ──────────────────────────────────────────────

@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Return the authenticated user's profile.

    Requires a valid Bearer JWT. Never returns password_hash.
    """
    return current_user
