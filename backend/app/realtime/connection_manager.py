"""WebSocket Connection Manager and Redis Pub/Sub delivery bridge with strict tenant isolation."""

import asyncio
from dataclasses import dataclass
import json
import logging
from typing import Dict, List, Optional, Set
import uuid

from fastapi import WebSocket, WebSocketDisconnect

from app.models.user import User, UserRole
from app.realtime.redis import redis_manager

logger = logging.getLogger("coldchain.realtime.manager")


@dataclass
class ActiveClient:
    """Represents an authenticated, active WebSocket connection."""

    websocket: WebSocket
    user_id: uuid.UUID
    email: str
    role: UserRole
    organization_id: Optional[uuid.UUID]
    # For SUPER_ADMIN: optional filter for a specific organization
    filter_org_id: Optional[uuid.UUID] = None

    @property
    def is_super_admin(self) -> bool:
        return self.role == UserRole.SUPER_ADMIN


class ConnectionManager:
    """Manages active WebSockets and delivers tenant-filtered telemetry events."""

    def __init__(self) -> None:
        self._clients: List[ActiveClient] = []
        self._lock = asyncio.Lock()
        self._subscriber_task: Optional[asyncio.Task] = None
        self._running = False

    async def register(self, client: ActiveClient) -> None:
        """Register and accept a new authenticated WebSocket client."""
        async with self._lock:
            self._clients.append(client)
        logger.info(
            "WebSocket client connected: %s (role=%s, org=%s, active_total=%d)",
            client.email,
            client.role.value,
            client.organization_id,
            len(self._clients),
        )

    async def unregister(self, websocket: WebSocket) -> None:
        """Safely remove a disconnected client."""
        async with self._lock:
            self._clients = [c for c in self._clients if c.websocket != websocket]
        logger.info("WebSocket client unregistered (active_total=%d)", len(self._clients))

    async def broadcast_to_org(self, organization_id: str | uuid.UUID, event: dict) -> None:
        """Deliver a telemetry event strictly to authorized WebSocket clients.

        Tenant Isolation Guarantee:
          - Regular USER: Only receives event if client.organization_id == organization_id.
          - SUPER_ADMIN: Receives event across all tenants (or respects filter_org_id).
        """
        target_org_str = str(organization_id)
        async with self._lock:
            clients_snapshot = list(self._clients)

        dead_sockets: List[WebSocket] = []
        for client in clients_snapshot:
            # 1. Enforce Tenant Isolation
            if not client.is_super_admin:
                if str(client.organization_id) != target_org_str:
                    continue
            else:
                # SUPER_ADMIN: filter if client requested a specific org
                if client.filter_org_id is not None and str(client.filter_org_id) != target_org_str:
                    continue

            # 2. Transmit message safely
            try:
                await client.websocket.send_json(event)
            except (WebSocketDisconnect, RuntimeError, Exception) as exc:
                logger.debug("Failed sending to client %s (%s). Marking dead.", client.email, exc)
                dead_sockets.append(client.websocket)

        # 3. Clean up dead connections
        if dead_sockets:
            async with self._lock:
                self._clients = [c for c in self._clients if c.websocket not in dead_sockets]

    async def broadcast_ping(self) -> None:
        """Send a lightweight ping message to keep connections alive and identify dead sockets."""
        async with self._lock:
            clients_snapshot = list(self._clients)

        dead_sockets: List[WebSocket] = []
        for client in clients_snapshot:
            try:
                await client.websocket.send_json({"type": "ping"})
            except Exception:
                dead_sockets.append(client.websocket)

        if dead_sockets:
            async with self._lock:
                self._clients = [c for c in self._clients if c.websocket not in dead_sockets]

    def get_active_count(self) -> int:
        return len(self._clients)

    # ──────────────────────────────────────────────
    # Redis Pub/Sub Bridge
    # ──────────────────────────────────────────────

    async def start_redis_bridge(self) -> None:
        """Start background task listening to Redis Pub/Sub channels."""
        if self._subscriber_task is not None and not self._subscriber_task.done():
            return
        self._running = True
        self._subscriber_task = asyncio.create_task(self._redis_listener())
        logger.info("Redis-WebSocket subscriber bridge started.")

    async def stop_redis_bridge(self) -> None:
        """Stop the background Redis listener task."""
        self._running = False
        if self._subscriber_task is not None:
            self._subscriber_task.cancel()
            try:
                await self._subscriber_task
            except asyncio.CancelledError:
                pass
            self._subscriber_task = None
        logger.info("Redis-WebSocket subscriber bridge stopped.")

    async def _redis_listener(self) -> None:
        """Background loop reading from Redis Pub/Sub and bridging to WebSockets."""
        while self._running:
            try:
                client = redis_manager.get_async_client()
                if client is None:
                    await redis_manager.connect()
                    client = redis_manager.get_async_client()

                if client is None:
                    await asyncio.sleep(3.0)
                    continue

                pubsub = client.pubsub()
                await pubsub.psubscribe(redis_manager.get_telemetry_pattern())
                logger.info("Redis listener active on pattern %s", redis_manager.get_telemetry_pattern())

                while self._running:
                    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    if msg is not None and msg.get("type") == "pmessage":
                        try:
                            channel = msg.get("channel", "")
                            data_raw = msg.get("data")
                            data_parsed = json.loads(data_raw) if isinstance(data_raw, str) else data_raw

                            # Extract organization_id from channel: coldchain:telemetry:{org_id}
                            parts = channel.split(":")
                            if len(parts) >= 3:
                                org_id = parts[2]
                                await self.broadcast_to_org(org_id, data_parsed)
                        except Exception as exc:
                            logger.error("Error processing Redis telemetry message: %s", exc)

                    await asyncio.sleep(0.01)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Redis listener encountered error (%s). Reconnecting in 3s...", exc)
                await asyncio.sleep(3.0)


# Global connection manager instance
connection_manager = ConnectionManager()
