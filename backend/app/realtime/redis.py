"""Redis connection management, Pub/Sub channel naming, and event dispatch."""

import json
import logging
from typing import Any, Optional
import uuid

import redis
import redis.asyncio as aioredis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger("coldchain.realtime.redis")


class RedisManager:
    """Manages Redis connection pools for async Pub/Sub and sync publishing."""

    def __init__(self, url: Optional[str] = None) -> None:
        self.url = url or settings.REDIS_URL
        self._async_client: Optional[aioredis.Redis] = None
        self._sync_client: Optional[redis.Redis] = None
        self._is_connected = False

    @staticmethod
    def get_channel_for_org(organization_id: str | uuid.UUID) -> str:
        """Format the tenant-isolated Redis telemetry channel name."""
        return f"coldchain:telemetry:{str(organization_id)}"

    @staticmethod
    def get_telemetry_pattern() -> str:
        """Return pattern matching all tenant telemetry channels."""
        return "coldchain:telemetry:*"

    async def connect(self) -> None:
        """Initialize async Redis client and verify connectivity."""
        try:
            if self._async_client is None:
                self._async_client = aioredis.from_url(
                    self.url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=2.0,
                    socket_timeout=2.0,
                )
            await self._async_client.ping()
            self._is_connected = True
            logger.info("Connected to Redis at %s", self.url)
        except Exception as exc:
            self._is_connected = False
            logger.warning("Redis is currently unavailable (%s: %s). Real-time streaming disabled.", type(exc).__name__, exc)

    async def close(self) -> None:
        """Gracefully close Redis connections."""
        if self._async_client is not None:
            try:
                await self._async_client.aclose()
            except Exception as exc:
                logger.warning("Error closing async Redis client: %s", exc)
            self._async_client = None

        if self._sync_client is not None:
            try:
                self._sync_client.close()
            except Exception as exc:
                logger.warning("Error closing sync Redis client: %s", exc)
            self._sync_client = None

        self._is_connected = False
        logger.info("Redis connections closed.")

    async def ping(self) -> bool:
        """Check if Redis is reachable."""
        try:
            if self._async_client is None:
                self._async_client = aioredis.from_url(
                    self.url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=2.0,
                    socket_timeout=2.0,
                )
            await self._async_client.ping()
            self._is_connected = True
            return True
        except Exception:
            self._is_connected = False
            return False

    def get_async_client(self) -> Optional[aioredis.Redis]:
        """Return the async Redis client instance."""
        return self._async_client

    def _get_sync_client(self) -> redis.Redis:
        """Lazy-initialize and return synchronous Redis client."""
        if self._sync_client is None:
            self._sync_client = redis.from_url(
                self.url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=2.0,
                socket_timeout=2.0,
            )
        return self._sync_client

    async def publish(self, channel: str, message: dict | str) -> bool:
        """Publish an event asynchronously to a Redis channel.

        Returns True on success, False if Redis is unreachable. Never raises exceptions.
        """
        payload_str = json.dumps(message) if isinstance(message, dict) else message
        try:
            if self._async_client is None:
                await self.connect()
            if self._async_client is not None:
                await self._async_client.publish(channel, payload_str)
                logger.debug("Async published event to %s: %s", channel, payload_str[:120])
                return True
        except Exception as exc:
            logger.warning("Failed to async publish to Redis (%s): %s", channel, exc)
            self._is_connected = False
        return False

    def publish_sync(self, channel: str, message: dict | str) -> bool:
        """Publish an event synchronously to a Redis channel (for MQTT callback threads).

        Returns True on success, False if Redis is unreachable. Never raises exceptions.
        """
        payload_str = json.dumps(message) if isinstance(message, dict) else message
        try:
            client = self._get_sync_client()
            client.publish(channel, payload_str)
            logger.debug("Sync published event to %s: %s", channel, payload_str[:120])
            return True
        except Exception as exc:
            logger.warning("Failed to sync publish to Redis (%s): %s", channel, exc)
            self._is_connected = False
        return False


# Global singleton Redis manager
redis_manager = RedisManager()
