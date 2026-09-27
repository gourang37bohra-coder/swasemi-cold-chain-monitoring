"""Unit and integration tests for MQTT Telemetry Ingestion and Query APIs."""

from datetime import datetime, timezone
import json
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import engine
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.organization import Organization
from app.models.shipment import Shipment, ShipmentStatus
from app.models.telemetry import Telemetry
from app.models.tracker import Tracker
from app.models.user import User, UserRole
from app.services.telemetry_ingestion import ingest_telemetry_payload


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db_session():
    """Provides a database session with entity tracking and auto-cleanup."""
    connection = engine.connect()
    session = Session(bind=connection)
    cleanup_telemetry_ids = []
    cleanup_shipment_ids = []
    cleanup_tracker_ids = []
    cleanup_user_ids = []
    cleanup_org_ids = []

    yield session, cleanup_org_ids, cleanup_user_ids, cleanup_tracker_ids, cleanup_shipment_ids, cleanup_telemetry_ids

    # Teardown in reverse dependency order
    if cleanup_telemetry_ids:
        session.query(Telemetry).filter(Telemetry.id.in_(cleanup_telemetry_ids)).delete(synchronize_session=False)
        session.commit()
    if cleanup_shipment_ids:
        session.query(Shipment).filter(Shipment.id.in_(cleanup_shipment_ids)).delete(synchronize_session=False)
        session.commit()
    if cleanup_tracker_ids:
        session.query(Tracker).filter(Tracker.id.in_(cleanup_tracker_ids)).delete(synchronize_session=False)
        session.commit()
    if cleanup_user_ids:
        session.query(User).filter(User.id.in_(cleanup_user_ids)).delete(synchronize_session=False)
        session.commit()
    if cleanup_org_ids:
        session.query(Organization).filter(Organization.id.in_(cleanup_org_ids)).delete(synchronize_session=False)
        session.commit()

    session.close()
    connection.close()


def create_user_headers(session, org, role=UserRole.USER, user_tracker_list=None):
    user = User(
        email=f"user-{uuid.uuid4().hex[:8]}@test.com",
        password_hash=hash_password("Password123!"),
        organization_id=org.id if org else None,
        role=role,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    if user_tracker_list is not None:
        user_tracker_list.append(user.id)

    token = create_access_token(
        user_id=user.id,
        org_id=user.organization_id,
        role=user.role.value,
    )
    return user, {"Authorization": f"Bearer {token}"}


# ──────────────────────────────────────────────
# Telemetry Ingestion Tests
# ──────────────────────────────────────────────

def test_valid_telemetry_active_shipment_persisted(db_session):
    """Test 1: Valid telemetry for an ACTIVE shipment is successfully persisted."""
    session, org_ids, _, tracker_ids, shipment_ids, telemetry_ids = db_session

    org = Organization(name=f"Org-{uuid.uuid4().hex[:8]}")
    session.add(org)
    session.commit()
    org_ids.append(org.id)

    tracker = Tracker(organization_id=org.id, name="Sensor-01", mqtt_topic="devices/s1")
    session.add(tracker)
    session.commit()
    tracker_ids.append(tracker.id)

    shipment = Shipment(
        organization_id=org.id,
        tracker_id=tracker.id,
        status=ShipmentStatus.ACTIVE,
        started_at=datetime.now(timezone.utc),
        minimum_temperature=2.0,
        maximum_temperature=8.0,
    )
    session.add(shipment)
    session.commit()
    shipment_ids.append(shipment.id)

    read_time = datetime.now(timezone.utc)
    raw_payload = json.dumps({
        "tracker_id": str(tracker.id),
        "timestamp": read_time.isoformat(),
        "temperature": 4.5,
        "latitude": 37.7749,
        "longitude": -122.4194,
        "humidity": 45.2,
        "battery": 92.0,
        "door_status": False,
    })

    result = ingest_telemetry_payload(session, raw_payload)
    assert result.success is True
    assert result.status == "ACCEPTED"
    assert result.telemetry is not None

    telemetry = result.telemetry
    telemetry_ids.append(telemetry.id)

    assert telemetry.organization_id == org.id
    assert telemetry.tracker_id == tracker.id
    assert telemetry.shipment_id == shipment.id
    assert telemetry.temperature == 4.5
    assert telemetry.latitude == 37.7749
    assert telemetry.longitude == -122.4194

    # Verify tracker last_seen updated
    session.refresh(tracker)
    assert tracker.last_seen is not None


def test_valid_telemetry_not_started_shipment_rejected(db_session):
    """Test 2: Telemetry for a NOT_STARTED shipment must NOT be persisted."""
    session, org_ids, _, tracker_ids, shipment_ids, _ = db_session

    org = Organization(name=f"Org-{uuid.uuid4().hex[:8]}")
    session.add(org)
    session.commit()
    org_ids.append(org.id)

    tracker = Tracker(organization_id=org.id, name="Sensor-02", mqtt_topic="devices/s2")
    session.add(tracker)
    session.commit()
    tracker_ids.append(tracker.id)

    shipment = Shipment(
        organization_id=org.id,
        tracker_id=tracker.id,
        status=ShipmentStatus.NOT_STARTED,
        minimum_temperature=2.0,
        maximum_temperature=8.0,
    )
    session.add(shipment)
    session.commit()
    shipment_ids.append(shipment.id)

    raw_payload = {
        "tracker_id": str(tracker.id),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "temperature": 4.0,
        "latitude": 40.7128,
        "longitude": -74.0060,
    }

    result = ingest_telemetry_payload(session, raw_payload)
    assert result.success is False
    assert result.status == "REJECTED_NO_ACTIVE_SHIPMENT"

    # Confirm no rows created in DB
    rows = session.scalars(select(Telemetry).where(Telemetry.tracker_id == tracker.id)).all()
    assert len(list(rows)) == 0

    session.refresh(tracker)
    assert tracker.last_seen is None


def test_valid_telemetry_completed_shipment_rejected(db_session):
    """Test 3: Telemetry for a COMPLETED shipment must NOT be persisted."""
    session, org_ids, _, tracker_ids, shipment_ids, _ = db_session

    org = Organization(name=f"Org-{uuid.uuid4().hex[:8]}")
    session.add(org)
    session.commit()
    org_ids.append(org.id)

    tracker = Tracker(organization_id=org.id, name="Sensor-03", mqtt_topic="devices/s3")
    session.add(tracker)
    session.commit()
    tracker_ids.append(tracker.id)

    shipment = Shipment(
        organization_id=org.id,
        tracker_id=tracker.id,
        status=ShipmentStatus.COMPLETED,
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
        minimum_temperature=2.0,
        maximum_temperature=8.0,
    )
    session.add(shipment)
    session.commit()
    shipment_ids.append(shipment.id)

    raw_payload = {
        "tracker_id": str(tracker.id),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "temperature": 5.1,
        "latitude": 51.5074,
        "longitude": -0.1278,
    }

    result = ingest_telemetry_payload(session, raw_payload)
    assert result.success is False
    assert result.status == "REJECTED_NO_ACTIVE_SHIPMENT"

    rows = session.scalars(select(Telemetry).where(Telemetry.tracker_id == tracker.id)).all()
    assert len(list(rows)) == 0


def test_tracker_does_not_exist_rejected(db_session):
    """Test 4: Telemetry referencing a non-existent tracker is rejected."""
    session, _, _, _, _, _ = db_session

    fake_tracker_id = uuid.uuid4()
    raw_payload = {
        "tracker_id": str(fake_tracker_id),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "temperature": 3.0,
        "latitude": 48.8566,
        "longitude": 2.3522,
    }

    result = ingest_telemetry_payload(session, raw_payload)
    assert result.success is False
    assert result.status == "REJECTED_UNKNOWN_TRACKER"


def test_tracker_exists_but_no_shipments_rejected(db_session):
    """Test 5: Tracker exists but has no shipments at all -> rejected."""
    session, org_ids, _, tracker_ids, _, _ = db_session

    org = Organization(name=f"Org-{uuid.uuid4().hex[:8]}")
    session.add(org)
    session.commit()
    org_ids.append(org.id)

    tracker = Tracker(organization_id=org.id, name="UnassignedSensor", mqtt_topic="devices/free")
    session.add(tracker)
    session.commit()
    tracker_ids.append(tracker.id)

    raw_payload = {
        "tracker_id": str(tracker.id),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "temperature": 6.2,
        "latitude": 35.6762,
        "longitude": 139.6503,
    }

    result = ingest_telemetry_payload(session, raw_payload)
    assert result.success is False
    assert result.status == "REJECTED_NO_ACTIVE_SHIPMENT"


def test_malformed_json_safely_rejected(db_session):
    """Test 6: Malformed JSON payload is rejected safely without exception."""
    session, _, _, _, _, _ = db_session

    bad_payload = b"this is not { valid json at all!"
    result = ingest_telemetry_payload(session, bad_payload)
    assert result.success is False
    assert result.status == "REJECTED_INVALID_JSON"


def test_invalid_telemetry_schema_rejected(db_session):
    """Test 7: Telemetry missing required fields or invalid coordinates rejected."""
    session, _, _, _, _, _ = db_session

    # Invalid latitude (> 90 degrees)
    bad_coords = {
        "tracker_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "temperature": 4.0,
        "latitude": 150.0,
        "longitude": 20.0,
    }
    result = ingest_telemetry_payload(session, bad_coords)
    assert result.success is False
    assert result.status == "REJECTED_SCHEMA_VALIDATION"


def test_cross_org_spoofing_prevented(db_session):
    """Test 8: Spoofed organization_id in payload is strictly ignored."""
    session, org_ids, _, tracker_ids, shipment_ids, telemetry_ids = db_session

    real_org = Organization(name=f"RealOrg-{uuid.uuid4().hex[:8]}")
    attacker_org = Organization(name=f"AttackerOrg-{uuid.uuid4().hex[:8]}")
    session.add_all([real_org, attacker_org])
    session.commit()
    org_ids.extend([real_org.id, attacker_org.id])

    tracker = Tracker(organization_id=real_org.id, name="RealSensor", mqtt_topic="devices/real")
    session.add(tracker)
    session.commit()
    tracker_ids.append(tracker.id)

    shipment = Shipment(
        organization_id=real_org.id,
        tracker_id=tracker.id,
        status=ShipmentStatus.ACTIVE,
        started_at=datetime.now(timezone.utc),
        minimum_temperature=2.0,
        maximum_temperature=8.0,
    )
    session.add(shipment)
    session.commit()
    shipment_ids.append(shipment.id)

    # Injected spoofed org_id
    payload = {
        "tracker_id": str(tracker.id),
        "organization_id": str(attacker_org.id),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "temperature": 3.8,
        "latitude": 30.0,
        "longitude": 31.0,
    }

    result = ingest_telemetry_payload(session, payload)
    assert result.success is True
    assert result.telemetry.organization_id == real_org.id
    assert result.telemetry.organization_id != attacker_org.id
    telemetry_ids.append(result.telemetry.id)


def test_idempotent_duplicate_telemetry_ignored(db_session):
    """Test 9: Identical readings with the same (tracker_id, timestamp) are ignored gracefully."""
    session, org_ids, _, tracker_ids, shipment_ids, telemetry_ids = db_session

    org = Organization(name=f"Org-{uuid.uuid4().hex[:8]}")
    session.add(org)
    session.commit()
    org_ids.append(org.id)

    tracker = Tracker(organization_id=org.id, name="IdempotentSensor", mqtt_topic="devices/idem")
    session.add(tracker)
    session.commit()
    tracker_ids.append(tracker.id)

    shipment = Shipment(
        organization_id=org.id,
        tracker_id=tracker.id,
        status=ShipmentStatus.ACTIVE,
        started_at=datetime.now(timezone.utc),
        minimum_temperature=2.0,
        maximum_temperature=8.0,
    )
    session.add(shipment)
    session.commit()
    shipment_ids.append(shipment.id)

    event_time = datetime.now(timezone.utc)
    payload = {
        "tracker_id": str(tracker.id),
        "timestamp": event_time.isoformat(),
        "temperature": 5.0,
        "latitude": 10.0,
        "longitude": 20.0,
    }

    # First send -> ACCEPTED
    res1 = ingest_telemetry_payload(session, payload)
    assert res1.success is True
    assert res1.status == "ACCEPTED"
    telemetry_ids.append(res1.telemetry.id)

    # Second send with identical tracker & timestamp -> IGNORED_DUPLICATE
    res2 = ingest_telemetry_payload(session, payload)
    assert res2.success is True
    assert res2.status == "IGNORED_DUPLICATE"

    # Verify only 1 record exists in DB
    all_readings = session.scalars(select(Telemetry).where(Telemetry.tracker_id == tracker.id)).all()
    assert len(list(all_readings)) == 1


# ──────────────────────────────────────────────
# Telemetry Query API Tests
# ──────────────────────────────────────────────

def test_telemetry_query_api_tenant_isolated(client: TestClient, db_session):
    """Test 10: GET /telemetry is strictly tenant isolated."""
    session, org_ids, user_ids, tracker_ids, shipment_ids, telemetry_ids = db_session

    org_a = Organization(name=f"OrgA-{uuid.uuid4().hex[:8]}")
    org_b = Organization(name=f"OrgB-{uuid.uuid4().hex[:8]}")
    session.add_all([org_a, org_b])
    session.commit()
    org_ids.extend([org_a.id, org_b.id])

    _, headers_a = create_user_headers(session, org_a, UserRole.USER, user_ids)
    _, headers_b = create_user_headers(session, org_b, UserRole.USER, user_ids)
    _, admin_headers = create_user_headers(session, None, UserRole.SUPER_ADMIN, user_ids)

    # Setup tracker and shipment for Org A
    tracker_a = Tracker(organization_id=org_a.id, name="TA", mqtt_topic="ta")
    session.add(tracker_a)
    session.commit()
    tracker_ids.append(tracker_a.id)

    shipment_a = Shipment(
        organization_id=org_a.id,
        tracker_id=tracker_a.id,
        status=ShipmentStatus.ACTIVE,
        minimum_temperature=2.0,
        maximum_temperature=8.0,
    )
    session.add(shipment_a)
    session.commit()
    shipment_ids.append(shipment_a.id)

    telem_a = Telemetry(
        organization_id=org_a.id,
        tracker_id=tracker_a.id,
        shipment_id=shipment_a.id,
        temperature=4.0,
        humidity=50.0,
        battery=90.0,
        door_status=False,
        latitude=10.0,
        longitude=10.0,
        timestamp=datetime.now(timezone.utc),
    )
    session.add(telem_a)
    session.commit()
    telemetry_ids.append(telem_a.id)

    # Setup tracker and shipment for Org B
    tracker_b = Tracker(organization_id=org_b.id, name="TB", mqtt_topic="tb")
    session.add(tracker_b)
    session.commit()
    tracker_ids.append(tracker_b.id)

    shipment_b = Shipment(
        organization_id=org_b.id,
        tracker_id=tracker_b.id,
        status=ShipmentStatus.ACTIVE,
        minimum_temperature=2.0,
        maximum_temperature=8.0,
    )
    session.add(shipment_b)
    session.commit()
    shipment_ids.append(shipment_b.id)

    telem_b = Telemetry(
        organization_id=org_b.id,
        tracker_id=tracker_b.id,
        shipment_id=shipment_b.id,
        temperature=7.0,
        humidity=60.0,
        battery=80.0,
        door_status=True,
        latitude=20.0,
        longitude=20.0,
        timestamp=datetime.now(timezone.utc),
    )
    session.add(telem_b)
    session.commit()
    telemetry_ids.append(telem_b.id)

    # User A only sees Telemetry A
    res_a = client.get("/telemetry", headers=headers_a)
    assert res_a.status_code == 200
    ids_a = [item["id"] for item in res_a.json()["items"]]
    assert str(telem_a.id) in ids_a
    assert str(telem_b.id) not in ids_a

    # User B only sees Telemetry B
    res_b = client.get("/telemetry", headers=headers_b)
    assert res_b.status_code == 200
    ids_b = [item["id"] for item in res_b.json()["items"]]
    assert str(telem_b.id) in ids_b
    assert str(telem_a.id) not in ids_b

    # Super Admin can see both
    res_admin = client.get("/telemetry", headers=admin_headers)
    assert res_admin.status_code == 200
    ids_admin = [item["id"] for item in res_admin.json()["items"]]
    assert str(telem_a.id) in ids_admin
    assert str(telem_b.id) in ids_admin

    # Filter by tracker_id
    res_filter = client.get(f"/telemetry?tracker_id={tracker_a.id}", headers=headers_a)
    assert res_filter.status_code == 200
    assert len(res_filter.json()["items"]) == 1
    assert res_filter.json()["items"][0]["tracker_id"] == str(tracker_a.id)
