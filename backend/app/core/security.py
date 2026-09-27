"""Password hashing and JWT token utilities."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import bcrypt
import jwt
from jwt.exceptions import DecodeError, ExpiredSignatureError, InvalidTokenError

from app.core.config import settings

logger = logging.getLogger("coldchain.security")

# ──────────────────────────────────────────────
# Password Hashing
# ──────────────────────────────────────────────

def hash_password(plain_password: str) -> str:
    """Return a bcrypt hash of the plaintext password.

    The plaintext password is never stored or logged.
    """
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Return True if the plaintext password matches the stored bcrypt hash."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        password_hash.encode("utf-8"),
    )


# ──────────────────────────────────────────────
# JWT Token Creation
# ──────────────────────────────────────────────

def create_access_token(
    *,
    user_id: UUID,
    org_id: UUID | None,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT containing user identity, organization, and role.

    Claims:
      sub  – user UUID (string)
      org_id – organization UUID or None for SUPER_ADMIN (string | null)
      role – user role string
      exp  – expiration timestamp
      iat  – issued-at timestamp
    """
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "org_id": str(org_id) if org_id is not None else None,
        "role": role,
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


# ──────────────────────────────────────────────
# JWT Token Decoding & Validation
# ──────────────────────────────────────────────

class TokenValidationError(Exception):
    """Raised when a JWT cannot be decoded or is missing required claims."""


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT.

    Returns the payload dict with at minimum: sub, org_id, role.

    Raises TokenValidationError for expired, malformed, or invalid tokens.
    Never logs the token value itself.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except ExpiredSignatureError:
        raise TokenValidationError("Token has expired.")
    except (DecodeError, InvalidTokenError) as exc:
        raise TokenValidationError(f"Invalid token: {type(exc).__name__}")

    for required in ("sub", "role"):
        if payload.get(required) is None:
            raise TokenValidationError(f"Token missing required claim: {required}")

    return payload
