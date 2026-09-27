"""Tests for Model 7: Redis Pub/Sub, WebSocket Real-Time Telemetry, and Tenant Isolation."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.organization import Organization
from app.models.shipment import Shipment, ShipmentStatus
from app.models.telemetry import Telemetry
from app.models.tracker import Tracker, TrackerStatus
from app.models.user import User, UserRole
from app.realtime.connection_manager import connection_manager
from app.realtime.events import publish_telemetry_event, serialize_telemetry_event
from app.realtime.redis import RedisManager, redis_manager
from app.services.telemetry_ingestion import ingest_telemetry_payload


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def test_data():
    """Sets up an organization, super-admin, user, tracker, and active shipment."""
    session = SessionLocal()
    org_a = Organization(name=f"RealtimeOrgA-{uuid.uuid4().hex[:6]}")
    org_b = Organization(name=f"RealtimeOrgB-{uuid.uuid4().hex[:6]}")
    session.add_all([org_a, org_b])
    session.commit()

    # Users
    user_a = User(
        email=f"usera-{uuid.uuid4().hex[:6]}@example.com",
        password_hash=hash_password("Password123!"),
        organization_id=org_a.id,
        role=UserRole.USER,
    )
    user_b = User(
        email=f"userb-{uuid.uuid4().hex[:6]}@example.com",
        password_hash=hash_password("Password123!"),
        organization_id=org_b.id,
        role=UserRole.USER,
    )
    admin_user = User(
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        password_hash=hash_password("Password123!"),
        organization_id=None,
        role=UserRole.SUPER_ADMIN,
    )
    session.add_all([user_a, user_b, admin_user])
    session.commit()

    # Tracker & Active Shipment for Org A
    tracker_a = Tracker(
        organization_id=org_a.id,
        name="RT Tracker Alpha",
        mqtt_topic="coldchain/trackers/rt-001/telemetry",
        status=TrackerStatus.ONLINE,
    )
    session.add(tracker_a)
    session.commit()

    shipment_a = Shipment(
        organization_id=org_a.id,
        tracker_id=tracker_a.id,
        status=ShipmentStatus.ACTIVE,
        minimum_temperature=2.0,
        maximum_temperature=8.0,
        grace_readings=2,
    )
    session.add(shipment_a)
    session.commit()

    # JWT Tokens
    token_a = create_access_token(user_id=user_a.id, org_id=org_a.id, role="USER")
    token_b = create_access_token(user_id=user_b.id, org_id=org_b.id, role="USER")
    token_admin = create_access_token(user_id=admin_user.id, org_id=None, role="SUPER_ADMIN")

    yield {
        "session": session,
        "org_a": org_a,
        "org_b": org_b,
        "user_a": user_a,
        "user_b": user_b,
        "admin_user": admin_user,
        "tracker_a": tracker_a,
        "shipment_a": shipment_a,
        "token_a": token_a,
        "token_b": token_b,
        "token_admin": token_admin,
    }

    # Cleanup in reverse foreign key order
    session.query(Telemetry).filter(Telemetry.organization_id.in_([org_a.id, org_b.id])).delete(synchronize_session=False)
    session.query(Shipment).filter(Shipment.organization_id.in_([org_a.id, org_b.id])).delete(synchronize_session=False)
    session.query(Tracker).filter(Tracker.organization_id.in_([org_a.id, org_b.id])).delete(synchronize_session=False)
    session.query(User).filter(User.id.in_([user_a.id, user_b.id, admin_user.id])).delete(synchronize_session=False)
    session.query(Organization).filter(Organization.id.in_([org_a.id, org_b.id])).delete(synchronize_session=False)
    session.commit()
    session.close()


# ──────────────────────────────────────────────
# 1. Redis Configuration & Serialization Tests
# ──────────────────────────────────────────────

def test_redis_configuration_loads():
    """Verify REDIS_URL configuration is loaded properly."""
    assert hasattr(settings, "REDIS_URL")
    assert settings.REDIS_URL.startswith("redis://")


def test_redis_channel_naming_format(test_data):
    """Verify tenant telemetry channel conforms to specification."""
    channel = RedisManager.get_channel_for_org(test_data["org_a"].id)
    assert channel == f"coldchain:telemetry:{test_data['org_a'].id}"
    assert RedisManager.get_telemetry_pattern() == "coldchain:telemetry:*"


def test_serialize_telemetry_event(test_data):
    """Verify event serialization includes all required telemetry attributes as strings/numbers."""
    now = datetime.now(timezone.utc)
    telem = Telemetry(
        id=uuid.uuid4(),
        organization_id=test_data["org_a"].id,
        tracker_id=test_data["tracker_a"].id,
        shipment_id=test_data["shipment_a"].id,
        temperature=4.5,
        humidity=60.0,
        battery=95.0,
        door_status=False,
        latitude=19.0760,
        longitude=72.8777,
        timestamp=now,
    )
    event = serialize_telemetry_event(telem)
    assert event["type"] == "telemetry.updated"
    data = event["data"]
    assert data["id"] == str(telem.id)
    assert data["organization_id"] == str(test_data["org_a"].id)
    assert data["tracker_id"] == str(test_data["tracker_a"].id)
    assert data["shipment_id"] == str(test_data["shipment_a"].id)
    assert data["temperature"] == 4.5
    assert data["latitude"] == 19.0760
    assert data["longitude"] == 72.8777
    assert data["timestamp"] == now.isoformat()


# ──────────────────────────────────────────────
# 2. Redis Persistence & Failure Behavior Tests
# ──────────────────────────────────────────────

def test_telemetry_persisted_when_redis_available(test_data):
    """Verify telemetry persists and publishes when Redis is reachable (mocked)."""
    session = test_data["session"]
    payload = {
        "tracker_id": str(test_data["tracker_a"].id),
        "temperature": 5.2,
        "humidity": 55.0,
        "battery": 90.0,
        "door_status": False,
        "latitude": 19.1234,
        "longitude": 72.8500,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    with patch.object(redis_manager, "publish_sync", return_value=True) as mock_pub:
        result = ingest_telemetry_payload(session, payload)
        assert result.success is True
        assert result.status == "ACCEPTED"
        mock_pub.assert_called_once()
        channel = mock_pub.call_args[0][0]
        assert channel == f"coldchain:telemetry:{test_data['org_a'].id}"


def test_telemetry_persisted_when_redis_unavailable(test_data):
    """CRITICAL: Database persistence must NOT fail when Redis is down."""
    session = test_data["session"]
    payload = {
        "tracker_id": str(test_data["tracker_a"].id),
        "temperature": 3.8,
        "humidity": 58.0,
        "battery": 88.0,
        "door_status": False,
        "latitude": 19.1234,
        "longitude": 72.8500,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    with patch.object(redis_manager, "publish_sync", side_effect=Exception("Redis Connection Refused")):
        result = ingest_telemetry_payload(session, payload)
        assert result.success is True
        assert result.status == "ACCEPTED"
        assert result.telemetry is not None
        # Verify row exists in PostgreSQL
        saved = session.get(Telemetry, result.telemetry.id)
        assert saved is not None
        assert saved.temperature == 3.8


# ──────────────────────────────────────────────
# 3. WebSocket Authentication & Rejection Tests
# ──────────────────────────────────────────────

def test_websocket_requires_authentication(client):
    """Connecting without token is rejected with 1008."""
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/telemetry"):
            pass
    assert exc.value.code == 1008


def test_websocket_rejects_invalid_token(client):
    """Connecting with malformed token is rejected with 1008."""
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/telemetry?token=invalid.jwt.token"):
            pass
    assert exc.value.code == 1008


def test_websocket_rejects_expired_token(client, test_data):
    """Connecting with expired token is rejected with 1008."""
    expired_token = create_access_token(
        user_id=test_data["user_a"].id,
        org_id=test_data["org_a"].id,
        role="USER",
        expires_delta=datetime.now(timezone.utc) - datetime.now(timezone.utc),  # zero lifetime
    )
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/ws/telemetry?token={expired_token}"):
            pass
    assert exc.value.code == 1008


# ──────────────────────────────────────────────
# 4. WebSocket Tenant Isolation & Delivery Tests
# ──────────────────────────────────────────────

def test_websocket_user_connection_success(client, test_data):
    """Authenticated user connects successfully and receives welcome event."""
    with client.websocket_connect(f"/ws/telemetry?token={test_data['token_a']}") as ws:
        event = ws.receive_json()
        assert event["type"] == "connection.established"
        assert event["data"]["role"] == "USER"
        assert event["data"]["organization_id"] == str(test_data["org_a"].id)


def test_websocket_user_tenant_isolation(client, test_data):
    """USER cannot subscribe to another tenant even if query parameter is sent."""
    # User A passes Org B's ID in query param
    with client.websocket_connect(
        f"/ws/telemetry?token={test_data['token_a']}&organization_id={test_data['org_b'].id}"
    ) as ws:
        event = ws.receive_json()
        # Server must ignore the client-provided org and bind strictly to Org A
        assert event["data"]["organization_id"] == str(test_data["org_a"].id)
        assert event["data"]["filter_organization_id"] is None


def test_websocket_super_admin_connection_and_filter(client, test_data):
    """SUPER_ADMIN can connect with platform-wide scope or optional filter."""
    with client.websocket_connect(f"/ws/telemetry?token={test_data['token_admin']}") as ws:
        event = ws.receive_json()
        assert event["type"] == "connection.established"
        assert event["data"]["role"] == "SUPER_ADMIN"
        assert event["data"]["organization_id"] is None

    # With optional filter
    with client.websocket_connect(
        f"/ws/telemetry?token={test_data['token_admin']}&organization_id={test_data['org_a'].id}"
    ) as ws:
        event = ws.receive_json()
        assert event["data"]["filter_organization_id"] == str(test_data["org_a"].id)


def test_websocket_receives_telemetry_event(client, test_data):
    """Connected client receives real-time telemetry event for their organization."""
    with client.websocket_connect(f"/ws/telemetry?token={test_data['token_a']}") as ws:
        welcome = ws.receive_json()
        assert welcome["type"] == "connection.established"

        # Broadcast telemetry for Org A
        event_payload = {
            "type": "telemetry.updated",
            "data": {
                "tracker_id": str(test_data["tracker_a"].id),
                "temperature": 4.1,
                "latitude": 19.076,
                "longitude": 72.877,
            },
        }

        # Deliver via connection manager to Org A
        asyncio.run(connection_manager.broadcast_to_org(test_data["org_a"].id, event_payload))

        received = ws.receive_json()
        assert received["type"] == "telemetry.updated"
        assert received["data"]["temperature"] == 4.1


def test_websocket_cross_tenant_message_never_delivered_to_other_org(client, test_data):
    """Org B user never receives Org A's telemetry event."""
    with client.websocket_connect(f"/ws/telemetry?token={test_data['token_b']}") as ws_b:
        welcome = ws_b.receive_json()
        assert welcome["data"]["organization_id"] == str(test_data["org_b"].id)

        # Broadcast telemetry for Org A
        event_org_a = {
            "type": "telemetry.updated",
            "data": {"tracker_id": "trk-a", "temperature": 4.1},
        }
        asyncio.run(connection_manager.broadcast_to_org(test_data["org_a"].id, event_org_a))

        # Ping-pong check: User B can ping/pong, but did not receive Org A event
        ws_b.send_json({"type": "ping"})
        reply = ws_b.receive_json()
        assert reply["type"] == "pong"  # User B received pong, NOT Org A telemetry


def test_websocket_heartbeat_ping_pong(client, test_data):
    """Client can send ping and receive pong heartbeat."""
    with client.websocket_connect(f"/ws/telemetry?token={test_data['token_a']}") as ws:
        ws.receive_json()  # welcome
        ws.send_json({"type": "ping"})
        pong = ws.receive_json()
        assert pong == {"type": "pong"}


def test_multiple_websocket_clients_receive_events(client, test_data):
    """Multiple connected clients under the same organization receive the telemetry event."""
    with client.websocket_connect(f"/ws/telemetry?token={test_data['token_a']}") as ws1:
        with client.websocket_connect(f"/ws/telemetry?token={test_data['token_a']}") as ws2:
            ws1.receive_json()  # welcome ws1
            ws2.receive_json()  # welcome ws2

            event_payload = {
                "type": "telemetry.updated",
                "data": {
                    "tracker_id": str(test_data["tracker_a"].id),
                    "temperature": 6.8,
                },
            }
            asyncio.run(connection_manager.broadcast_to_org(test_data["org_a"].id, event_payload))

            msg1 = ws1.receive_json()
            msg2 = ws2.receive_json()
            assert msg1["type"] == "telemetry.updated" and msg1["data"]["temperature"] == 6.8
            assert msg2["type"] == "telemetry.updated" and msg2["data"]["temperature"] == 6.8


def test_disconnected_clients_removed_safely(client, test_data):
    """When a client socket disconnects, it is safely unregistered and broadcast does not crash."""
    initial_count = connection_manager.get_active_count()
    with client.websocket_connect(f"/ws/telemetry?token={test_data['token_a']}") as ws:
        ws.receive_json()  # welcome
        assert connection_manager.get_active_count() == initial_count + 1

    # Now exited the context -> socket closed
    assert connection_manager.get_active_count() == initial_count

    # Broadcast to that org should execute cleanly with 0 exceptions
    asyncio.run(connection_manager.broadcast_to_org(test_data["org_a"].id, {"type": "telemetry.updated", "data": {}}))


# ──────────────────────────────────────────────
# 5. Redis Health Endpoint Tests
# ──────────────────────────────────────────────

def test_redis_health_check_available(client):
    """GET /health/redis returns 200 when Redis ping succeeds."""
    with patch.object(redis_manager, "ping", return_value=True):
        resp = client.get("/health/redis")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "redis": "connected"}


def test_redis_health_check_unavailable(client):
    """GET /health/redis returns 503 when Redis ping fails."""
    with patch.object(redis_manager, "ping", return_value=False):
        resp = client.get("/health/redis")
        assert resp.status_code == 503
        assert resp.json() == {"status": "error", "redis": "unavailable"}
