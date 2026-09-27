"""Comprehensive tests for Model 9: Historical shipment analysis, CSV export, and compliance alerts."""

from datetime import datetime, timezone
import io
import json
from unittest.mock import MagicMock, patch
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import engine
from app.core.security import create_access_token
from app.main import app
from app.models.alert import Alert, AlertType
from app.models.organization import Organization
from app.models.shipment import Shipment, ShipmentStatus
from app.models.telemetry import Telemetry
from app.models.tracker import Tracker, TrackerStatus
from app.models.user import User, UserRole
from app.services.compliance import evaluate_temperature_compliance
from app.services.email_service import email_service
from app.services.telemetry_ingestion import ingest_telemetry_payload


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db_session():
    """Provides a database session with entity tracking and auto-cleanup."""
    connection = engine.connect()
    session = Session(bind=connection)
    cleanup_alert_ids = []
    cleanup_telemetry_ids = []
    cleanup_shipment_ids = []
    cleanup_tracker_ids = []
    cleanup_user_ids = []
    cleanup_org_ids = []

    yield session, cleanup_org_ids, cleanup_user_ids, cleanup_tracker_ids, cleanup_shipment_ids, cleanup_telemetry_ids, cleanup_alert_ids

    # Teardown in reverse dependency order
    if cleanup_alert_ids:
        session.query(Alert).filter(Alert.id.in_(cleanup_alert_ids)).delete(synchronize_session=False)
        session.commit()
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


def create_tenant_setup(session, cleanup_tuple, name_prefix="m9"):
    """Helper creating an Org, User, Tracker, and Active Shipment."""
    (
        cleanup_org_ids,
        cleanup_user_ids,
        cleanup_tracker_ids,
        cleanup_shipment_ids,
        cleanup_telemetry_ids,
        cleanup_alert_ids,
    ) = cleanup_tuple

    org = Organization(name=f"Org-{name_prefix}-{uuid.uuid4().hex[:6]}")
    session.add(org)
    session.commit()
    session.refresh(org)
    cleanup_org_ids.append(org.id)

    user = User(
        email=f"user-{name_prefix}-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="fakehash",
        role=UserRole.USER,
        organization_id=org.id,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    cleanup_user_ids.append(user.id)

    tracker = Tracker(
        organization_id=org.id,
        name=f"Tracker-{name_prefix}",
        mqtt_topic=f"coldchain/trackers/{uuid.uuid4()}/telemetry",
        status=TrackerStatus.ONLINE,
    )
    session.add(tracker)
    session.commit()
    session.refresh(tracker)
    cleanup_tracker_ids.append(tracker.id)

    shipment = Shipment(
        organization_id=org.id,
        tracker_id=tracker.id,
        status=ShipmentStatus.ACTIVE,
        started_at=datetime.now(timezone.utc),
        minimum_temperature=2.0,
        maximum_temperature=8.0,
        grace_readings=3,
        consecutive_violations=0,
        breach_active=False,
    )
    session.add(shipment)
    session.commit()
    session.refresh(shipment)
    cleanup_shipment_ids.append(shipment.id)

    user_token = create_access_token(
        user_id=user.id, org_id=org.id, role=user.role.value
    )

    return org, user, tracker, shipment, user_token


# ──────────────────────────────────────────────
# 1. Historical Shipment Detail & Metrics API
# ──────────────────────────────────────────────

def test_historical_shipment_detail_and_metrics(client, db_session):
    session, *cleanup_tuple = db_session
    org, user, tracker, shipment, token = create_tenant_setup(session, cleanup_tuple, "hist")

    # Add 2 telemetry readings
    now = datetime.now(timezone.utc)
    t1 = Telemetry(
        organization_id=org.id,
        tracker_id=tracker.id,
        shipment_id=shipment.id,
        temperature=4.0,
        humidity=50.0,
        battery=99.0,
        door_status=False,
        latitude=19.1000,
        longitude=72.8500,
        timestamp=now,
    )
    t2 = Telemetry(
        organization_id=org.id,
        tracker_id=tracker.id,
        shipment_id=shipment.id,
        temperature=6.0,
        humidity=52.0,
        battery=98.0,
        door_status=False,
        latitude=19.1100,
        longitude=72.8600,
        timestamp=now,
    )
    session.add_all([t1, t2])
    session.commit()
    cleanup_tuple[4].extend([t1.id, t2.id])

    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get(f"/shipments/{shipment.id}/history", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["shipment"]["id"] == str(shipment.id)
    assert data["metrics"]["reading_count"] == 2
    assert data["metrics"]["min_temperature"] == 4.0
    assert data["metrics"]["max_temperature"] == 6.0
    assert data["metrics"]["avg_temperature"] == 5.0
    assert data["metrics"]["duration_seconds"] is not None

    # Test full telemetry listing
    telem_resp = client.get(f"/shipments/{shipment.id}/telemetry", headers=headers)
    assert telem_resp.status_code == 200
    assert len(telem_resp.json()) == 2


# ──────────────────────────────────────────────
# 2. Tenant Isolation on History and CSV
# ──────────────────────────────────────────────

def test_tenant_isolation_on_history_and_csv(client, db_session):
    session, *cleanup_tuple = db_session
    org_a, user_a, tracker_a, shipment_a, token_a = create_tenant_setup(session, cleanup_tuple, "orga")
    org_b, user_b, tracker_b, shipment_b, token_b = create_tenant_setup(session, cleanup_tuple, "orgb")

    sa_user = User(
        email=f"admin-{uuid.uuid4().hex[:6]}@swasemi.com",
        password_hash="fakehash",
        role=UserRole.SUPER_ADMIN,
        organization_id=None,
    )
    session.add(sa_user)
    session.commit()
    session.refresh(sa_user)
    cleanup_tuple[1].append(sa_user.id)

    super_admin_token = create_access_token(
        user_id=sa_user.id, org_id=None, role="SUPER_ADMIN"
    )

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}
    headers_sa = {"Authorization": f"Bearer {super_admin_token}"}

    # User A CAN access Shipment A
    res_a = client.get(f"/shipments/{shipment_a.id}/history", headers=headers_a)
    assert res_a.status_code == 200

    # User A CANNOT access Shipment B (returns 404 Zero-Knowledge)
    res_a_b = client.get(f"/shipments/{shipment_b.id}/history", headers=headers_a)
    assert res_a_b.status_code == 404

    # User A CANNOT export Shipment B CSV
    res_csv_a_b = client.get(f"/shipments/{shipment_b.id}/export.csv", headers=headers_a)
    assert res_csv_a_b.status_code == 404

    # SUPER_ADMIN CAN access Shipment A and B history & CSV
    res_sa_a = client.get(f"/shipments/{shipment_a.id}/history", headers=headers_sa)
    assert res_sa_a.status_code == 200
    res_sa_b_csv = client.get(f"/shipments/{shipment_b.id}/export.csv", headers=headers_sa)
    assert res_sa_b_csv.status_code == 200


# ──────────────────────────────────────────────
# 3. CSV Export Content and Formatting
# ──────────────────────────────────────────────

def test_csv_export_content_and_headers(client, db_session):
    session, *cleanup_tuple = db_session
    org, user, tracker, shipment, token = create_tenant_setup(session, cleanup_tuple, "csv")

    # Add a telemetry record
    t = Telemetry(
        organization_id=org.id,
        tracker_id=tracker.id,
        shipment_id=shipment.id,
        temperature=4.85,
        humidity=55.2,
        battery=95.0,
        door_status=False,
        latitude=19.123456,
        longitude=72.654321,
        timestamp=datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc),
    )
    session.add(t)
    session.commit()
    cleanup_tuple[4].append(t.id)

    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get(f"/shipments/{shipment.id}/export.csv", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert f'filename="shipment_{shipment.id}_telemetry.csv"' in resp.headers["content-disposition"]

    csv_text = resp.text
    lines = [line.strip() for line in csv_text.strip().split("\n") if line.strip()]
    assert len(lines) == 2  # Header + 1 record
    assert lines[0] == "timestamp,tracker_id,shipment_id,temperature,humidity,battery,door_status,latitude,longitude"
    assert str(tracker.id) in lines[1]
    assert "4.85" in lines[1]
    assert "closed" in lines[1]
    assert "19.123456" in lines[1]


# ──────────────────────────────────────────────
# 4. Temperature Profile Validation
# ──────────────────────────────────────────────

def test_temperature_profile_validation(client, db_session):
    session, *cleanup_tuple = db_session
    org, user, tracker, _, token = create_tenant_setup(session, cleanup_tuple, "val")

    headers = {"Authorization": f"Bearer {token}"}

    # Minimum >= Maximum rejected
    resp_invalid_temp = client.post(
        "/shipments",
        headers=headers,
        json={
            "tracker_id": str(tracker.id),
            "minimum_temperature": 10.0,
            "maximum_temperature": 5.0,
            "grace_readings": 2,
        },
    )
    assert resp_invalid_temp.status_code == 422

    # Grace readings < 1 rejected
    resp_invalid_grace = client.post(
        "/shipments",
        headers=headers,
        json={
            "tracker_id": str(tracker.id),
            "minimum_temperature": 2.0,
            "maximum_temperature": 8.0,
            "grace_readings": 0,
        },
    )
    assert resp_invalid_grace.status_code == 422


# ──────────────────────────────────────────────
# 5. In-Range Temperature Produces No Breach
# ──────────────────────────────────────────────

def test_in_range_temperature_creates_no_breach(db_session):
    session, *cleanup_tuple = db_session
    org, user, tracker, shipment, _ = create_tenant_setup(session, cleanup_tuple, "safe")

    telemetry = Telemetry(
        organization_id=org.id,
        tracker_id=tracker.id,
        shipment_id=shipment.id,
        temperature=5.0,  # inside [2.0, 8.0]
        humidity=50.0,
        battery=100.0,
        door_status=False,
        latitude=19.0,
        longitude=72.0,
        timestamp=datetime.now(timezone.utc),
    )
    session.add(telemetry)
    session.commit()
    cleanup_tuple[4].append(telemetry.id)

    alert = evaluate_temperature_compliance(session, shipment, tracker, telemetry)
    assert alert is None
    assert shipment.consecutive_violations == 0
    assert not shipment.breach_active


# ──────────────────────────────────────────────
# 6. Grace Period Progression and Alert Trigger
# ──────────────────────────────────────────────

@patch.object(email_service, "send_breach_alert", return_value=True)
def test_grace_period_and_breach_alert_trigger(mock_email, db_session):
    session, *cleanup_tuple = db_session
    org, user, tracker, shipment, _ = create_tenant_setup(session, cleanup_tuple, "grace")
    shipment.grace_readings = 3
    session.commit()

    now = datetime.now(timezone.utc)

    # Reading 1: 12.0°C (Violation 1) -> No alert
    t1 = Telemetry(
        organization_id=org.id, tracker_id=tracker.id, shipment_id=shipment.id,
        temperature=12.0, humidity=50.0, battery=98.0, door_status=False,
        latitude=19.0, longitude=72.0, timestamp=now,
    )
    session.add(t1)
    session.commit()
    cleanup_tuple[4].append(t1.id)

    alert1 = evaluate_temperature_compliance(session, shipment, tracker, t1)
    assert alert1 is None
    assert shipment.consecutive_violations == 1
    assert not shipment.breach_active
    assert mock_email.call_count == 0

    # Reading 2: 12.5°C (Violation 2) -> No alert
    t2 = Telemetry(
        organization_id=org.id, tracker_id=tracker.id, shipment_id=shipment.id,
        temperature=12.5, humidity=50.0, battery=97.0, door_status=False,
        latitude=19.01, longitude=72.01, timestamp=now,
    )
    session.add(t2)
    session.commit()
    cleanup_tuple[4].append(t2.id)

    alert2 = evaluate_temperature_compliance(session, shipment, tracker, t2)
    assert alert2 is None
    assert shipment.consecutive_violations == 2
    assert not shipment.breach_active
    assert mock_email.call_count == 0

    # Reading 3: 13.0°C (Violation 3 == grace_readings) -> Confirmed breach!
    t3 = Telemetry(
        organization_id=org.id, tracker_id=tracker.id, shipment_id=shipment.id,
        temperature=13.0, humidity=50.0, battery=96.0, door_status=False,
        latitude=19.02, longitude=72.02, timestamp=now,
    )
    session.add(t3)
    session.commit()
    cleanup_tuple[4].append(t3.id)

    alert3 = evaluate_temperature_compliance(session, shipment, tracker, t3)
    assert alert3 is not None
    cleanup_tuple[5].append(alert3.id)
    assert alert3.type == AlertType.TEMPERATURE_BREACH
    assert alert3.temperature == 13.0
    assert shipment.breach_active is True
    assert shipment.consecutive_violations == 3
    assert mock_email.call_count == 1


# ──────────────────────────────────────────────
# 7. Continuous Breach Suppresses Duplicate Emails
# ──────────────────────────────────────────────

@patch.object(email_service, "send_breach_alert", return_value=True)
def test_continuous_breach_suppresses_duplicate_alerts(mock_email, db_session):
    session, *cleanup_tuple = db_session
    org, user, tracker, shipment, _ = create_tenant_setup(session, cleanup_tuple, "suppress")
    shipment.grace_readings = 1
    session.commit()

    now = datetime.now(timezone.utc)

    # Reading 1: triggers breach
    t1 = Telemetry(
        organization_id=org.id, tracker_id=tracker.id, shipment_id=shipment.id,
        temperature=14.0, humidity=50.0, battery=95.0, door_status=False,
        latitude=19.0, longitude=72.0, timestamp=now,
    )
    session.add(t1)
    session.commit()
    cleanup_tuple[4].append(t1.id)

    alert1 = evaluate_temperature_compliance(session, shipment, tracker, t1)
    assert alert1 is not None
    cleanup_tuple[5].append(alert1.id)
    assert shipment.breach_active is True
    assert mock_email.call_count == 1

    # Reading 2: continuous violation -> MUST NOT SEND SECOND EMAIL OR CREATE SECOND ALERT
    t2 = Telemetry(
        organization_id=org.id, tracker_id=tracker.id, shipment_id=shipment.id,
        temperature=15.0, humidity=50.0, battery=94.0, door_status=False,
        latitude=19.01, longitude=72.01, timestamp=now,
    )
    session.add(t2)
    session.commit()
    cleanup_tuple[4].append(t2.id)

    alert2 = evaluate_temperature_compliance(session, shipment, tracker, t2)
    assert alert2 is None  # Suppressed!
    assert shipment.breach_active is True
    assert shipment.consecutive_violations == 2
    assert mock_email.call_count == 1  # Still exactly 1 email!


# ──────────────────────────────────────────────
# 8. Safe Temperature Resets Continuous Breach
# ──────────────────────────────────────────────

@patch.object(email_service, "send_breach_alert", return_value=True)
def test_in_range_temperature_resets_breach_and_allows_subsequent_alert(mock_email, db_session):
    session, *cleanup_tuple = db_session
    org, user, tracker, shipment, _ = create_tenant_setup(session, cleanup_tuple, "reset")
    shipment.grace_readings = 1
    session.commit()

    now = datetime.now(timezone.utc)

    # 1. Breach 1
    t1 = Telemetry(
        organization_id=org.id, tracker_id=tracker.id, shipment_id=shipment.id,
        temperature=11.0, humidity=50.0, battery=95.0, door_status=False,
        latitude=19.0, longitude=72.0, timestamp=now,
    )
    session.add(t1)
    session.commit()
    cleanup_tuple[4].append(t1.id)
    alert1 = evaluate_temperature_compliance(session, shipment, tracker, t1)
    assert alert1 is not None
    cleanup_tuple[5].append(alert1.id)
    assert shipment.breach_active is True

    # 2. In-range recovery (5.0°C) -> resets state
    t_safe = Telemetry(
        organization_id=org.id, tracker_id=tracker.id, shipment_id=shipment.id,
        temperature=5.0, humidity=50.0, battery=95.0, door_status=False,
        latitude=19.0, longitude=72.0, timestamp=now,
    )
    session.add(t_safe)
    session.commit()
    cleanup_tuple[4].append(t_safe.id)
    evaluate_temperature_compliance(session, shipment, tracker, t_safe)
    assert shipment.consecutive_violations == 0
    assert shipment.breach_active is False

    # 3. Breach 2: subsequent new breach can alert again!
    t2 = Telemetry(
        organization_id=org.id, tracker_id=tracker.id, shipment_id=shipment.id,
        temperature=12.0, humidity=50.0, battery=94.0, door_status=False,
        latitude=19.0, longitude=72.0, timestamp=now,
    )
    session.add(t2)
    session.commit()
    cleanup_tuple[4].append(t2.id)
    alert2 = evaluate_temperature_compliance(session, shipment, tracker, t2)
    assert alert2 is not None
    cleanup_tuple[5].append(alert2.id)
    assert alert2.id != alert1.id
    assert mock_email.call_count == 2


# ──────────────────────────────────────────────
# 9. Email Failure Does Not Crash Ingestion
# ──────────────────────────────────────────────

@patch("smtplib.SMTP", side_effect=ConnectionRefusedError("Simulated SMTP server down"))
def test_email_failure_does_not_block_ingestion(mock_smtp, db_session):
    session, *cleanup_tuple = db_session
    org, user, tracker, shipment, _ = create_tenant_setup(session, cleanup_tuple, "fail")
    shipment.grace_readings = 1
    session.commit()

    raw_payload = {
        "tracker_id": str(tracker.id),
        "temperature": 15.0,  # Excursion!
        "humidity": 55.0,
        "battery": 90.0,
        "door_status": False,
        "latitude": 19.1234,
        "longitude": 72.5678,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    result = ingest_telemetry_payload(session, raw_payload)
    assert result.success is True
    assert result.status == "ACCEPTED"
    cleanup_tuple[4].append(result.telemetry.id)

    # Verify telemetry was safely persisted in PostgreSQL despite email failure
    saved_telemetry = session.scalar(select(Telemetry).where(Telemetry.id == result.telemetry.id))
    assert saved_telemetry is not None

    # Verify alert was safely saved in PostgreSQL
    saved_alert = session.scalar(select(Alert).where(Alert.shipment_id == shipment.id))
    assert saved_alert is not None
    cleanup_tuple[5].append(saved_alert.id)


# ──────────────────────────────────────────────
# 10. Alerts API with Tenant Scoping
# ──────────────────────────────────────────────

def test_alerts_api_tenant_scoping(client, db_session):
    session, *cleanup_tuple = db_session
    org_a, user_a, tracker_a, shipment_a, token_a = create_tenant_setup(session, cleanup_tuple, "alrta")
    org_b, user_b, tracker_b, shipment_b, token_b = create_tenant_setup(session, cleanup_tuple, "alrtb")

    # Create alert for Org A
    alert_a = Alert(
        organization_id=org_a.id,
        shipment_id=shipment_a.id,
        tracker_id=tracker_a.id,
        type=AlertType.TEMPERATURE_BREACH,
        message="Org A breach",
        temperature=12.5,
        triggered_at=datetime.now(timezone.utc),
    )
    session.add(alert_a)
    session.commit()
    cleanup_tuple[5].append(alert_a.id)

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User A sees Alert A
    res_a = client.get("/alerts", headers=headers_a)
    assert res_a.status_code == 200
    assert res_a.json()["total"] == 1
    assert res_a.json()["items"][0]["id"] == str(alert_a.id)

    # User B sees 0 alerts (tenant isolated)
    res_b = client.get("/alerts", headers=headers_b)
    assert res_b.status_code == 200
    assert res_b.json()["total"] == 0

    # User A shipment alerts endpoint
    res_ship_a = client.get(f"/shipments/{shipment_a.id}/alerts", headers=headers_a)
    assert res_ship_a.status_code == 200
    assert len(res_ship_a.json()) == 1

    # User B cannot access shipment A alerts
    res_ship_b_a = client.get(f"/shipments/{shipment_a.id}/alerts", headers=headers_b)
    assert res_ship_b_a.status_code == 404
