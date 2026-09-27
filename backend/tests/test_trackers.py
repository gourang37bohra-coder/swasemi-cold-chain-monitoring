"""Tracker API and multi-tenant isolation tests for Model 4."""

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
# Tracker API Tests
# ──────────────────────────────────────────────

def test_user_creates_tracker(client: TestClient, db_session):
    """Test 1: USER creates a tracker scoped to their organization."""
    session, org_ids, user_ids, tracker_ids, _ = db_session

    org = Organization(name=f"Org-{uuid.uuid4().hex[:8]}")
    session.add(org)
    session.commit()
    org_ids.append(org.id)

    _, headers = create_user_and_headers(session, org, UserRole.USER, user_ids)

    payload = {
        "name": "Fridge-Unit-A1",
        "mqtt_topic": "devices/tracker-a1/telemetry",
        "status": "ONLINE",
    }
    response = client.post("/trackers", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()

    assert data["name"] == payload["name"]
    assert data["mqtt_topic"] == payload["mqtt_topic"]
    assert data["status"] == "ONLINE"
    assert data["organization_id"] == str(org.id)
    assert "id" in data
    assert "created_at" in data
    tracker_ids.append(uuid.UUID(data["id"]))


def test_user_lists_own_trackers(client: TestClient, db_session):
    """Test 2: USER lists only trackers belonging to their organization."""
    session, org_ids, user_ids, tracker_ids, _ = db_session

    org1 = Organization(name=f"Org1-{uuid.uuid4().hex[:8]}")
    org2 = Organization(name=f"Org2-{uuid.uuid4().hex[:8]}")
    session.add_all([org1, org2])
    session.commit()
    org_ids.extend([org1.id, org2.id])

    _, headers1 = create_user_and_headers(session, org1, UserRole.USER, user_ids)

    # Tracker in Org1
    t1 = Tracker(organization_id=org1.id, name="T1", mqtt_topic="t1", status=TrackerStatus.ONLINE)
    # Tracker in Org2
    t2 = Tracker(organization_id=org2.id, name="T2", mqtt_topic="t2", status=TrackerStatus.ONLINE)
    session.add_all([t1, t2])
    session.commit()
    tracker_ids.extend([t1.id, t2.id])

    res = client.get("/trackers", headers=headers1)
    assert res.status_code == 200
    data = res.json()

    returned_ids = [item["id"] for item in data["items"]]
    assert str(t1.id) in returned_ids
    assert str(t2.id) not in returned_ids
    assert data["total"] == 1


def test_user_gets_own_tracker(client: TestClient, db_session):
    """Test 3: USER can retrieve details of their own tracker."""
    session, org_ids, user_ids, tracker_ids, _ = db_session

    org = Organization(name=f"Org-{uuid.uuid4().hex[:8]}")
    session.add(org)
    session.commit()
    org_ids.append(org.id)

    _, headers = create_user_and_headers(session, org, UserRole.USER, user_ids)
    t = Tracker(organization_id=org.id, name="ColdBox-1", mqtt_topic="cb1", status=TrackerStatus.OFFLINE)
    session.add(t)
    session.commit()
    tracker_ids.append(t.id)

    res = client.get(f"/trackers/{t.id}", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == str(t.id)
    assert data["name"] == "ColdBox-1"


def test_user_cannot_access_other_org_tracker(client: TestClient, db_session):
    """Test 4: USER receives 404 when attempting to get another organization's tracker (zero-knowledge)."""
    session, org_ids, user_ids, tracker_ids, _ = db_session

    org_a = Organization(name=f"OrgA-{uuid.uuid4().hex[:8]}")
    org_b = Organization(name=f"OrgB-{uuid.uuid4().hex[:8]}")
    session.add_all([org_a, org_b])
    session.commit()
    org_ids.extend([org_a.id, org_b.id])

    _, headers_a = create_user_and_headers(session, org_a, UserRole.USER, user_ids)
    tracker_b = Tracker(organization_id=org_b.id, name="TB", mqtt_topic="tb")
    session.add(tracker_b)
    session.commit()
    tracker_ids.append(tracker_b.id)

    res = client.get(f"/trackers/{tracker_b.id}", headers=headers_a)
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_user_cannot_modify_other_org_tracker(client: TestClient, db_session):
    """Test 5: USER receives 404 when attempting to patch another organization's tracker."""
    session, org_ids, user_ids, tracker_ids, _ = db_session

    org_a = Organization(name=f"OrgA-{uuid.uuid4().hex[:8]}")
    org_b = Organization(name=f"OrgB-{uuid.uuid4().hex[:8]}")
    session.add_all([org_a, org_b])
    session.commit()
    org_ids.extend([org_a.id, org_b.id])

    _, headers_a = create_user_and_headers(session, org_a, UserRole.USER, user_ids)
    tracker_b = Tracker(organization_id=org_b.id, name="TB", mqtt_topic="tb")
    session.add(tracker_b)
    session.commit()
    tracker_ids.append(tracker_b.id)

    res = client.patch(f"/trackers/{tracker_b.id}", json={"name": "HackedName"}, headers=headers_a)
    assert res.status_code == 404


def test_user_cannot_delete_other_org_tracker(client: TestClient, db_session):
    """Test 6: USER receives 404 when attempting to delete another organization's tracker."""
    session, org_ids, user_ids, tracker_ids, _ = db_session

    org_a = Organization(name=f"OrgA-{uuid.uuid4().hex[:8]}")
    org_b = Organization(name=f"OrgB-{uuid.uuid4().hex[:8]}")
    session.add_all([org_a, org_b])
    session.commit()
    org_ids.extend([org_a.id, org_b.id])

    _, headers_a = create_user_and_headers(session, org_a, UserRole.USER, user_ids)
    tracker_b = Tracker(organization_id=org_b.id, name="TB", mqtt_topic="tb")
    session.add(tracker_b)
    session.commit()
    tracker_ids.append(tracker_b.id)

    res = client.delete(f"/trackers/{tracker_b.id}", headers=headers_a)
    assert res.status_code == 404


def test_super_admin_can_access_any_org_tracker(client: TestClient, db_session):
    """Test 7: SUPER_ADMIN can view and manage trackers across all organizations."""
    session, org_ids, user_ids, tracker_ids, _ = db_session

    org = Organization(name=f"Org-{uuid.uuid4().hex[:8]}")
    session.add(org)
    session.commit()
    org_ids.append(org.id)

    _, admin_headers = create_user_and_headers(session, None, UserRole.SUPER_ADMIN, user_ids)
    tracker = Tracker(organization_id=org.id, name="CrossOrgTracker", mqtt_topic="cot")
    session.add(tracker)
    session.commit()
    tracker_ids.append(tracker.id)

    res = client.get(f"/trackers/{tracker.id}", headers=admin_headers)
    assert res.status_code == 200
    assert res.json()["name"] == "CrossOrgTracker"


def test_trackers_pagination(client: TestClient, db_session):
    """Test 8: Tracker list pagination with page and page_size."""
    session, org_ids, user_ids, tracker_ids, _ = db_session

    org = Organization(name=f"Org-{uuid.uuid4().hex[:8]}")
    session.add(org)
    session.commit()
    org_ids.append(org.id)

    _, headers = create_user_and_headers(session, org, UserRole.USER, user_ids)

    # Create 5 trackers
    new_trackers = [
        Tracker(organization_id=org.id, name=f"Tracker-{i}", mqtt_topic=f"topic-{i}")
        for i in range(5)
    ]
    session.add_all(new_trackers)
    session.commit()
    tracker_ids.extend([t.id for t in new_trackers])

    # Request page 1 with page_size=2
    res = client.get("/trackers?page=1&page_size=2", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert data["total"] == 5

    # Request page 3 with page_size=2
    res_p3 = client.get("/trackers?page=3&page_size=2", headers=headers)
    assert res_p3.status_code == 200
    assert len(res_p3.json()["items"]) == 1


def test_invalid_jwt_rejected_on_trackers(client: TestClient):
    """Test 9: Endpoints reject invalid/missing JWT."""
    res_no_auth = client.get("/trackers")
    assert res_no_auth.status_code == 401

    res_bad_auth = client.get("/trackers", headers={"Authorization": "Bearer badtoken"})
    assert res_bad_auth.status_code == 401


def test_tracker_delete_restrict_constraint(client: TestClient, db_session):
    """Verify that deleting a tracker with associated shipments returns 409 Conflict."""
    session, org_ids, user_ids, tracker_ids, shipment_ids = db_session

    org = Organization(name=f"Org-{uuid.uuid4().hex[:8]}")
    session.add(org)
    session.commit()
    org_ids.append(org.id)

    _, headers = create_user_and_headers(session, org, UserRole.USER, user_ids)
    tracker = Tracker(organization_id=org.id, name="TrackerBound", mqtt_topic="tb")
    session.add(tracker)
    session.commit()
    tracker_ids.append(tracker.id)

    shipment = Shipment(
        organization_id=org.id,
        tracker_id=tracker.id,
        status=ShipmentStatus.NOT_STARTED,
        minimum_temperature=2.0,
        maximum_temperature=8.0,
        grace_readings=2,
    )
    session.add(shipment)
    session.commit()
    shipment_ids.append(shipment.id)

    # Deleting the tracker should fail with 409 Conflict due to FK RESTRICT
    res = client.delete(f"/trackers/{tracker.id}", headers=headers)
    assert res.status_code == 409
    assert "associated shipments" in res.json()["detail"].lower()


def test_tracker_delete_success_when_unreferenced(client: TestClient, db_session):
    """Verify that deleting an unreferenced tracker succeeds with 204."""
    session, org_ids, user_ids, tracker_ids, _ = db_session

    org = Organization(name=f"Org-{uuid.uuid4().hex[:8]}")
    session.add(org)
    session.commit()
    org_ids.append(org.id)

    _, headers = create_user_and_headers(session, org, UserRole.USER, user_ids)
    tracker = Tracker(organization_id=org.id, name="TrackerFree", mqtt_topic="tf")
    session.add(tracker)
    session.commit()

    res = client.delete(f"/trackers/{tracker.id}", headers=headers)
    assert res.status_code == 204

    # Verify tracker is gone
    check = session.scalar(select(Tracker).where(Tracker.id == tracker.id))
    assert check is None
