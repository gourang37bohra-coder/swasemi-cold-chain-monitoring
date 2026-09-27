"""FastAPI authentication and tenant-authorization dependencies."""

import logging
import uuid
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import TokenValidationError, decode_access_token
from app.models.user import User, UserRole

logger = logging.getLogger("coldchain.auth")

# Bearer scheme – auto-returns 403 on missing header (we override with 401 below)
_bearer_scheme = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or missing authentication credentials.",
    headers={"WWW-Authenticate": "Bearer"},
)


# ──────────────────────────────────────────────
# Core Authentication Dependency
# ──────────────────────────────────────────────

async def get_current_user(
    credentials: Annotated[
        Optional[HTTPAuthorizationCredentials], Depends(_bearer_scheme)
    ],
    db: Session = Depends(get_db),
) -> User:
    """Validate the Bearer JWT and return the corresponding database User.

    Steps:
      1. Require an Authorization: Bearer <token> header.
      2. Decode and validate the JWT.
      3. Extract sub (user_id), org_id, role.
      4. Confirm the user still exists in the database.
      5. Confirm the JWT role matches the stored role.
      6. Confirm org_id matches for USER accounts.
    """
    if credentials is None:
        raise _UNAUTHORIZED

    try:
        payload = decode_access_token(credentials.credentials)
    except TokenValidationError as exc:
        logger.warning("JWT validation failed: %s", exc)
        raise _UNAUTHORIZED

    user_id_str: str = payload["sub"]
    token_role: str = payload["role"]
    token_org_id: Optional[str] = payload.get("org_id")

    try:
        user_uuid = uuid.UUID(user_id_str)
    except ValueError:
        raise _UNAUTHORIZED

    user: Optional[User] = db.scalar(select(User).where(User.id == user_uuid))
    if user is None:
        raise _UNAUTHORIZED

    # Role must match the stored value – prevents token replay after role change
    if user.role.value != token_role:
        logger.warning("JWT role mismatch for user %s", user_uuid)
        raise _UNAUTHORIZED

    # Organization context check for normal USER accounts
    if user.role == UserRole.USER:
        expected_org = str(user.organization_id) if user.organization_id else None
        if token_org_id != expected_org:
            logger.warning("JWT org_id mismatch for user %s", user_uuid)
            raise _UNAUTHORIZED

    return user


# ──────────────────────────────────────────────
# Tenant Authorization Helpers
# ──────────────────────────────────────────────

class TenantContext:
    """Resolved tenant context for the current request.

    - For SUPER_ADMIN: organization_id is None; cross-org access is allowed.
    - For USER: organization_id is set to the user's organization; cross-org is denied.
    """

    def __init__(self, user: User) -> None:
        self.user = user
        self.is_super_admin = user.role == UserRole.SUPER_ADMIN
        self.organization_id: Optional[uuid.UUID] = (
            None if self.is_super_admin else user.organization_id
        )

    def assert_same_organization(self, resource_org_id: uuid.UUID) -> None:
        """Raise HTTP 403 if a normal USER attempts to access another organization's resource.

        SUPER_ADMIN bypasses this check.
        """
        if self.is_super_admin:
            return
        if self.organization_id != resource_org_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access to this resource is not permitted.",
            )


async def get_tenant_context(
    current_user: Annotated[User, Depends(get_current_user)],
) -> TenantContext:
    """Return a TenantContext for the current authenticated user.

    Future API endpoints inject this dependency to enforce organization scoping.
    """
    return TenantContext(current_user)


# Role-specific convenience dependencies
async def require_super_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Raise HTTP 403 unless the authenticated user is a SUPER_ADMIN."""
    if current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super-admin privileges required.",
        )
    return current_user
