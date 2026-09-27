"""Real-time WebSocket telemetry endpoint and Redis health router."""

import logging
from typing import Optional
import uuid

from fastapi import (
    APIRouter,
    Depends,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.core.security import TokenValidationError, decode_access_token
from app.models.user import User, UserRole
from app.realtime.connection_manager import ActiveClient, connection_manager
from app.realtime.redis import redis_manager

logger = logging.getLogger("coldchain.realtime.router")

router = APIRouter(tags=["Real-Time Telemetry"])


# ──────────────────────────────────────────────
# WebSocket Telemetry Endpoint
# ──────────────────────────────────────────────

@router.websocket("/ws/telemetry")
async def websocket_telemetry_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None, description="Bearer JWT access token for authentication"),
    organization_id: Optional[uuid.UUID] = Query(None, description="Optional org filter (SUPER_ADMIN only)"),
) -> None:
    """Real-time telemetry WebSocket stream.

    Authentication:
      - Requires a valid Bearer JWT via query param `?token=<access_token>`.
      - Missing, invalid, or expired tokens result in closure with code 1008 (Policy Violation).

    Tenant Isolation:
      - USER: Strictly bounded to the authenticated user's organization_id.
              Client-provided organization_id parameter is ignored.
      - SUPER_ADMIN: Can optionally filter by organization_id or receive all tenant events.
    """
    # 1. Require JWT token
    if not token:
        logger.warning("Rejected unauthenticated WebSocket connection attempt (missing token).")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication token is required.")
        return

    # 2. Decode and validate token
    try:
        payload = decode_access_token(token)
        user_id_str = payload.get("sub")
        token_role = payload.get("role")
        token_org_id = payload.get("org_id")
        user_uuid = uuid.UUID(user_id_str)
    except (TokenValidationError, ValueError, KeyError) as exc:
        logger.warning("Rejected WebSocket connection: Token validation failed (%s).", exc)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired authentication token.")
        return

    # 3. Verify user against database
    session = SessionLocal()
    try:
        user = session.scalar(select(User).where(User.id == user_uuid))
        if user is None:
            logger.warning("Rejected WebSocket connection: User %s not found in database.", user_uuid)
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="User account not found.")
            return

        if user.role.value != token_role:
            logger.warning("Rejected WebSocket connection: Role mismatch for user %s.", user_uuid)
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid credentials.")
            return

        # Derive effective organization scope server-side
        if user.role == UserRole.USER:
            effective_org_id = user.organization_id
            filter_org = None  # Regular USER cannot filter
        else:
            # SUPER_ADMIN: platform-wide, with optional filter
            effective_org_id = None
            filter_org = organization_id

        user_email = user.email
        user_role = user.role
    finally:
        session.close()

    # 4. Accept connection and register client
    await websocket.accept()
    client = ActiveClient(
        websocket=websocket,
        user_id=user_uuid,
        email=user_email,
        role=user_role,
        organization_id=effective_org_id,
        filter_org_id=filter_org,
    )
    await connection_manager.register(client)

    # 5. Send initial welcome event
    try:
        await websocket.send_json({
            "type": "connection.established",
            "data": {
                "user_id": str(user_uuid),
                "role": user_role.value,
                "organization_id": str(effective_org_id) if effective_org_id else None,
                "filter_organization_id": str(filter_org) if filter_org else None,
            },
        })
    except Exception as exc:
        logger.warning("Error sending welcome message: %s", exc)
        await connection_manager.unregister(websocket)
        return

    # 6. Keepalive & incoming message loop
    try:
        while True:
            data = await websocket.receive_json()
            # Handle client-initiated ping / heartbeat
            if isinstance(data, dict) and data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected normally: %s", user_email)
    except Exception as exc:
        logger.debug("WebSocket connection terminated (%s: %s)", type(exc).__name__, exc)
    finally:
        await connection_manager.unregister(websocket)


# ──────────────────────────────────────────────
# Redis Health Endpoint
# ──────────────────────────────────────────────

@router.get("/health/redis", tags=["Health"])
async def redis_health_check() -> JSONResponse:
    """Redis connectivity health check.

    Returns 200 OK when connected to Redis, or 503 Service Unavailable when unreachable.
    Does not expose Redis credentials or internal exception traces.
    """
    is_alive = await redis_manager.ping()
    if is_alive:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ok", "redis": "connected"},
        )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "error", "redis": "unavailable"},
    )
