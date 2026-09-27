"""Real-time telemetry event creation and serialization for Redis Pub/Sub."""

import logging
from typing import Any, Dict
import uuid

from app.models.alert import Alert
from app.models.telemetry import Telemetry
from app.realtime.redis import redis_manager

logger = logging.getLogger("coldchain.realtime.events")


def serialize_telemetry_event(telemetry: Telemetry) -> Dict[str, Any]:
    """Serialize a persisted Telemetry model into a safe JSON-ready dictionary."""
    return {
        "type": "telemetry.updated",
        "data": {
            "id": str(telemetry.id),
            "organization_id": str(telemetry.organization_id),
            "tracker_id": str(telemetry.tracker_id),
            "shipment_id": str(telemetry.shipment_id),
            "temperature": float(telemetry.temperature),
            "humidity": float(telemetry.humidity),
            "battery": float(telemetry.battery),
            "door_status": bool(telemetry.door_status),
            "latitude": float(telemetry.latitude),
            "longitude": float(telemetry.longitude),
            "timestamp": telemetry.timestamp.isoformat(),
        },
    }


def publish_telemetry_event(telemetry: Telemetry) -> bool:
    """Publish a telemetry event to the tenant's isolated Redis channel.

    Uses publish_sync so it can be called safely from MQTT threads, sync routes,
    or test fixtures without requiring an active async event loop in that thread.
    Catches all exceptions so database persistence is NEVER interrupted by Redis failure.
    """
    channel = redis_manager.get_channel_for_org(telemetry.organization_id)
    payload = serialize_telemetry_event(telemetry)
    try:
        return redis_manager.publish_sync(channel, payload)
    except Exception as exc:
        logger.warning(
            "Failed to publish telemetry event to Redis (%s): %s",
            channel,
            exc,
        )
        return False


def serialize_alert_event(alert: Alert) -> Dict[str, Any]:
    """Serialize a persisted Alert model into a safe JSON-ready dictionary."""
    return {
        "type": "alert.triggered",
        "data": {
            "id": str(alert.id),
            "organization_id": str(alert.organization_id),
            "shipment_id": str(alert.shipment_id),
            "tracker_id": str(alert.tracker_id),
            "type": alert.type.value if hasattr(alert.type, "value") else str(alert.type),
            "message": alert.message,
            "temperature": float(alert.temperature) if alert.temperature is not None else None,
            "triggered_at": alert.triggered_at.isoformat(),
            "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
        },
    }


def publish_alert_event(alert: Alert) -> bool:
    """Publish an alert event to the tenant's isolated Redis channel.

    Delivers instant notification over WebSocket to connected tenant users.
    Catches all exceptions so failure never disrupts caller execution.
    """
    channel = redis_manager.get_channel_for_org(alert.organization_id)
    payload = serialize_alert_event(alert)
    try:
        return redis_manager.publish_sync(channel, payload)
    except Exception as exc:
        logger.warning(
            "Failed to publish alert event to Redis (%s): %s",
            channel,
            exc,
        )
        return False

