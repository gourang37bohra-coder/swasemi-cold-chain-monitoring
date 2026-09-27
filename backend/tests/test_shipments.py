"""Shipment API, lifecycle state transitions, and multi-tenant tests for Model 4."""

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
from app.models.tracker import Tracker, TrackerStatus
from app.models.user import User, UserRole


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
    cleanup_shipment_ids = []
    cleanup_tracker_ids = []
    cleanup_user_ids = []
    cleanup_org_ids = []

    yield session, cleanup_org_ids, cleanup_user_ids, cleanup_tracker_ids, cleanup_shipment_ids

    # Cleanup in reverse foreign key order
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


def create_user_and_headers(session, org, role=UserRole.USER, user_tracker_list=None):
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
# Shipment Tests
# ──────────────────────────────────────────────

def test_user_creates_not_started_shipment(client: TestClient, db_session):
    """Tests 10 & 11: USER creates NOT_STARTED shipment referencing correct tracker."""
    session, org_ids, user_ids, tracker_ids, shipment_ids = db_session

    org = Organization(name=f"Org-{uuid.uuid4().hex[:8]}")
    session.add(org)
    session.commit()
    org_ids.append(org.id)

    _, headers = create_user_and_headers(session, org, UserRole.USER, user_ids)
    tracker = Tracker(organization_id=org.id, name="ColdTracker-1", mqtt_topic="ct1")
    session.add(tracker)
    session.commit()
    tracker_ids.append(tracker.id)

    payload = {
        "tracker_id": str(tracker.id),
        "minimum_temperature": 2.0,
        "maximum_temperature": 8.0,
        "grace_readings": 3,
    }
    response = client.post("/shipments", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()

    assert data["tracker_id"] == str(tracker.id)
    assert data["organization_id"] == str(org.id)
    assert data["status"] == "NOT_STARTED"
    assert data["started_at"] is None
    assert data["ended_at"] is None
    assert data["breach_active"] is False
    assert data["minimum_temperature"] == 2.0
    assert data["maximum_temperature"] == 8.0
    assert data["grace_readings"] == 3
    shipment_ids.append(uuid.UUID(data["id"]))


def test_user_cannot_create_shipment_with_other_org_tracker(client: TestClient, db_session):
    """Test 12: USER cannot create a shipment referencing a tracker from another organization."""
    session, org_ids, user_ids, tracker_ids, _ = db_session

    org_a = Organization(name=f"OrgA-{uuid.uuid4().hex[:8]}")
    org_b = Organization(name=f"OrgB-{uuid.uuid4().hex[:8]}")
    session.add_all([org_a, org_b])
    session.commit()
    org_ids.extend([org_a.id, org_b.id])

    _, headers_a = create_user_and_headers(session, org_a, UserRole.USER, user_ids)
    tracker_b = Tracker(organization_id=org_b.id, name="TrackerB", mqtt_topic="tb")
    session.add(tracker_b)
    session.commit()
    tracker_ids.append(tracker_b.id)

    payload = {
        "tracker_id": str(tracker_b.id),
        "minimum_temperature": 2.0,
        "maximum_temperature": 8.0,
        "grace_readings": 2,
    }
    response = client.post("/shipments", json=payload, headers=headers_a)
    # Tracker not found within Org A scope
    assert response.status_code == 404


def test_shipment_lifecycle_start_and_complete(client: TestClient, db_session):
    """Tests 13, 14, 15, 16, 17, 18, 19: Full state machine verification."""
    session, org_ids, user_ids, tracker_ids, shipment_ids = db_session

    org = Organization(name=f"Org-{uuid.uuid4().hex[:8]}")
    session.add(org)
    session.commit()
    org_ids.append(org.id)

    _, headers = create_user_and_headers(session, org, UserRole.USER, user_ids)
    tracker = Tracker(organization_id=org.id, name="LifecycleTracker", mqtt_topic="lt")
    session.add(tracker)
    session.commit()
    tracker_ids.append(tracker.id)

    # 1. Create NOT_STARTED shipment
    shipment = Shipment(
        organization_id=org.id,
        tracker_id=tracker.id,
        status=ShipmentStatus.NOT_STARTED,
        minimum_temperature=-20.0,
        maximum_temperature=-10.0,
        grace_readings=1,
    )
    session.add(shipment)
    session.commit()
    shipment_ids.append(shipment.id)

    # Test 19: Cannot complete a NOT_STARTED shipment directly
    res_premature_complete = client.post(f"/shipments/{shipment.id}/complete", headers=headers)
    assert res_premature_complete.status_code == 409
    assert "only active shipments can be completed" in res_premature_complete.json()["detail"].lower()

    # Test 13 & 14: Start shipment successfully -> sets ACTIVE and started_at
    res_start = client.post(f"/shipments/{shipment.id}/start", headers=headers)
    assert res_start.status_code == 200
    start_data = res_start.json()
    assert start_data["status"] == "ACTIVE"
    assert start_data["started_at"] is not None
    assert start_data["ended_at"] is None

    # Test 15: Cannot start an ACTIVE shipment again
    res_restart = client.post(f"/shipments/{shipment.id}/start", headers=headers)
    assert res_restart.status_code == 409
    assert "only not_started shipments can be started" in res_restart.json()["detail"].lower()

    # Test 16 & 17: Complete ACTIVE shipment -> sets COMPLETED and ended_at
    res_complete = client.post(f"/shipments/{shipment.id}/complete", headers=headers)
    assert res_complete.status_code == 200
    complete_data = res_complete.json()
    assert complete_data["status"] == "COMPLETED"
    assert complete_data["ended_at"] is not None

    # Test 18: Cannot restart or complete a COMPLETED shipment
    res_restart_completed = client.post(f"/shipments/{shipment.id}/start", headers=headers)
    assert res_restart_completed.status_code == 409

    res_recomplete = client.post(f"/shipments/{shipment.id}/complete", headers=headers)
    assert res_recomplete.status_code == 409


def test_user_cannot_access_other_org_shipment(client: TestClient, db_session):
    """Test 20: USER receives 404 when querying another organization's shipment."""
    session, org_ids, user_ids, tracker_ids, shipment_ids = db_session

    org_a = Organization(name=f"OrgA-{uuid.uuid4().hex[:8]}")
    org_b = Organization(name=f"OrgB-{uuid.uuid4().hex[:8]}")
    session.add_all([org_a, org_b])
    session.commit()
    org_ids.extend([org_a.id, org_b.id])

    _, headers_a = create_user_and_headers(session, org_a, UserRole.USER, user_ids)

    tracker_b = Tracker(organization_id=org_b.id, name="TrackerB", mqtt_topic="tb")
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

    # Org A user accessing Org B shipment returns 404
    res_get = client.get(f"/shipments/{shipment_b.id}", headers=headers_a)
    assert res_get.status_code == 404

    # Org A user starting Org B shipment returns 404
    res_start = client.post(f"/shipments/{shipment_b.id}/start", headers=headers_a)
    assert res_start.status_code == 404


def test_super_admin_can_access_other_org_shipment(client: TestClient, db_session):
    """Test 21: SUPER_ADMIN can query and manage shipments across organizations."""
    session, org_ids, user_ids, tracker_ids, shipment_ids = db_session

    org = Organization(name=f"Org-{uuid.uuid4().hex[:8]}")
    session.add(org)
    session.commit()
    org_ids.append(org.id)

    _, admin_headers = create_user_and_headers(session, None, UserRole.SUPER_ADMIN, user_ids)

    tracker = Tracker(organization_id=org.id, name="TrackerAdmin", mqtt_topic="ta")
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

    res = client.get(f"/shipments/{shipment.id}", headers=admin_headers)
    assert res.status_code == 200
    assert res.json()["id"] == str(shipment.id)


def test_temperature_validation(client: TestClient, db_session):
    """Test 22: minimum_temperature must be strictly less than maximum_temperature."""
    session, org_ids, user_ids, tracker_ids, _ = db_session

    org = Organization(name=f"Org-{uuid.uuid4().hex[:8]}")
    session.add(org)
    session.commit()
    org_ids.append(org.id)

    _, headers = create_user_and_headers(session, org, UserRole.USER, user_ids)
    tracker = Tracker(organization_id=org.id, name="TrackerT", mqtt_topic="tt")
    session.add(tracker)
    session.commit()
    tracker_ids.append(tracker.id)

    # Equal min and max -> rejected with 422
    res_equal = client.post(
        "/shipments",
        json={
            "tracker_id": str(tracker.id),
            "minimum_temperature": 5.0,
            "maximum_temperature": 5.0,
            "grace_readings": 1,
        },
        headers=headers,
    )
    assert res_equal.status_code == 422

    # min > max -> rejected with 422
    res_inverted = client.post(
        "/shipments",
        json={
            "tracker_id": str(tracker.id),
            "minimum_temperature": 10.0,
            "maximum_temperature": 2.0,
            "grace_readings": 1,
        },
        headers=headers,
    )
    assert res_inverted.status_code == 422


def test_grace_readings_validation(client: TestClient, db_session):
    """Test 23: grace_readings must be >= 1."""
    session, org_ids, user_ids, tracker_ids, _ = db_session

    org = Organization(name=f"Org-{uuid.uuid4().hex[:8]}")
    session.add(org)
    session.commit()
    org_ids.append(org.id)

    _, headers = create_user_and_headers(session, org, UserRole.USER, user_ids)
    tracker = Tracker(organization_id=org.id, name="TrackerG", mqtt_topic="tg")
    session.add(tracker)
    session.commit()
    tracker_ids.append(tracker.id)

    res_zero = client.post(
        "/shipments",
        json={
            "tracker_id": str(tracker.id),
            "minimum_temperature": 2.0,
            "maximum_temperature": 8.0,
            "grace_readings": 0,
        },
        headers=headers,
    )
    assert res_zero.status_code == 422

    res_negative = client.post(
        "/shipments",
        json={
            "tracker_id": str(tracker.id),
            "minimum_temperature": 2.0,
            "maximum_temperature": 8.0,
            "grace_readings": -3,
        },
        headers=headers,
    )
    assert res_negative.status_code == 422


def test_shipment_pagination(client: TestClient, db_session):
    """Test 24: Shipment list pagination with page and page_size."""
    session, org_ids, user_ids, tracker_ids, shipment_ids = db_session

    org = Organization(name=f"Org-{uuid.uuid4().hex[:8]}")
    session.add(org)
    session.commit()
    org_ids.append(org.id)

    _, headers = create_user_and_headers(session, org, UserRole.USER, user_ids)
    tracker = Tracker(organization_id=org.id, name="TrackerP", mqtt_topic="tp")
    session.add(tracker)
    session.commit()
    tracker_ids.append(tracker.id)

    new_shipments = [
        Shipment(
            organization_id=org.id,
            tracker_id=tracker.id,
            status=ShipmentStatus.NOT_STARTED,
            minimum_temperature=2.0 + i,
            maximum_temperature=10.0 + i,
            grace_readings=1,
        )
        for i in range(5)
    ]
    session.add_all(new_shipments)
    session.commit()
    shipment_ids.extend([s.id for s in new_shipments])

    # Page 1, size 2
    res_p1 = client.get("/shipments?page=1&page_size=2", headers=headers)
    assert res_p1.status_code == 200
    data_p1 = res_p1.json()
    assert len(data_p1["items"]) == 2
    assert data_p1["page"] == 1
    assert data_p1["page_size"] == 2
    assert data_p1["total"] == 5

    # Page 3, size 2
    res_p3 = client.get("/shipments?page=3&page_size=2", headers=headers)
    assert res_p3.status_code == 200
    assert len(res_p3.json()["items"]) == 1
