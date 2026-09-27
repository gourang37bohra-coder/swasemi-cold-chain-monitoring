"""Domain model and multi-tenant schema verification tests."""

import uuid
from datetime import datetime, timezone
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import engine
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.models.tracker import Tracker, TrackerStatus
from app.models.shipment import Shipment, ShipmentStatus
from app.models.telemetry import Telemetry
from app.models.alert import Alert, AlertType


@pytest.fixture
def db():
    """Provides a transactional database session rolled back after every test."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    if transaction.is_active:
        transaction.rollback()
    connection.close()


def test_create_organization(db: Session):
    """Test 1: Organization can be created with automatic timestamps and UUID."""
    org = Organization(name=f"BioLogistics-{uuid.uuid4().hex[:8]}")
    db.add(org)
    db.commit()

    saved_org = db.scalar(select(Organization).where(Organization.id == org.id))
    assert saved_org is not None
    assert saved_org.name == org.name
    assert saved_org.id is not None
    assert saved_org.created_at is not None
    assert saved_org.updated_at is not None


def test_organization_name_uniqueness(db: Session):
    """Test constraint: Duplicate organization names are rejected."""
    unique_name = f"PharmaCold-{uuid.uuid4().hex[:8]}"
    org1 = Organization(name=unique_name)
    org2 = Organization(name=unique_name)
    db.add(org1)
    db.commit()

    db.add(org2)
    with pytest.raises(IntegrityError):
        db.commit()


def test_create_user_with_organization(db: Session):
    """Test 2: User can reference an organization, and Super Admin can have null organization."""
    org = Organization(name=f"VaccineCorp-{uuid.uuid4().hex[:8]}")
    db.add(org)
    db.commit()

    # Regular tenant user
    user = User(
        organization_id=org.id,
        email=f"operator-{uuid.uuid4().hex[:8]}@vaccinecorp.com",
        password_hash="mocked_hashed_password_for_testing",
        role=UserRole.USER,
    )
    db.add(user)

    # Super admin without specific organization
    super_admin = User(
        organization_id=None,
        email=f"admin-{uuid.uuid4().hex[:8]}@swasemi.com",
        password_hash="mocked_hashed_password_for_testing",
        role=UserRole.SUPER_ADMIN,
    )
    db.add(super_admin)
    db.commit()

    saved_user = db.scalar(select(User).where(User.id == user.id))
    assert saved_user is not None
    assert saved_user.organization_id == org.id
    assert saved_user.organization.name == org.name
    assert saved_user.role == UserRole.USER

    saved_admin = db.scalar(select(User).where(User.id == super_admin.id))
    assert saved_admin is not None
    assert saved_admin.organization_id is None
    assert saved_admin.role == UserRole.SUPER_ADMIN


def test_user_email_uniqueness(db: Session):
    """Test constraint: Duplicate user emails are rejected."""
    email = f"duplicate-{uuid.uuid4().hex[:8]}@coldchain.com"
    user1 = User(
        email=email,
        password_hash="dummy_hash",
        role=UserRole.USER,
    )
    user2 = User(
        email=email,
        password_hash="dummy_hash",
        role=UserRole.USER,
    )
    db.add(user1)
    db.commit()

    db.add(user2)
    with pytest.raises(IntegrityError):
        db.commit()


def test_create_tracker_with_organization(db: Session):
    """Test 3: Tracker references organization with status and mqtt_topic."""
    org = Organization(name=f"FrostLogistics-{uuid.uuid4().hex[:8]}")
    db.add(org)
    db.commit()

    tracker = Tracker(
        organization_id=org.id,
        name="ColdBox-Sensor-01",
        mqtt_topic="devices/coldbox-01/telemetry",
        status=TrackerStatus.OFFLINE,
    )
    db.add(tracker)
    db.commit()

    saved_tracker = db.scalar(select(Tracker).where(Tracker.id == tracker.id))
    assert saved_tracker is not None
    assert saved_tracker.organization_id == org.id
    assert saved_tracker.organization.name == org.name
    assert saved_tracker.status == TrackerStatus.OFFLINE
    assert saved_tracker.mqtt_topic == "devices/coldbox-01/telemetry"


def test_create_shipment_with_organization_and_tracker(db: Session):
    """Test 4: Shipment references both organization and tracker, with temperature profile."""
    org = Organization(name=f"CryoTransport-{uuid.uuid4().hex[:8]}")
    db.add(org)
    db.commit()

    tracker = Tracker(
        organization_id=org.id,
        name="CryoTracker-A",
        mqtt_topic="devices/cryo-a/telemetry",
    )
    db.add(tracker)
    db.commit()

    shipment = Shipment(
        organization_id=org.id,
        tracker_id=tracker.id,
        status=ShipmentStatus.NOT_STARTED,
        minimum_temperature=2.0,
        maximum_temperature=8.0,
        grace_readings=3,
        breach_active=False,
    )
    db.add(shipment)
    db.commit()

    saved_shipment = db.scalar(select(Shipment).where(Shipment.id == shipment.id))
    assert saved_shipment is not None
    assert saved_shipment.organization_id == org.id
    assert saved_shipment.tracker_id == tracker.id
    assert saved_shipment.minimum_temperature == 2.0
    assert saved_shipment.maximum_temperature == 8.0
    assert saved_shipment.grace_readings == 3
    assert saved_shipment.breach_active is False
    assert saved_shipment.tracker.name == "CryoTracker-A"


def test_create_telemetry_record(db: Session):
    """Test 5: Telemetry references organization, shipment, and tracker."""
    org = Organization(name=f"ArcticCargo-{uuid.uuid4().hex[:8]}")
    db.add(org)
    db.commit()

    tracker = Tracker(
        organization_id=org.id,
        name="Tracker-AC1",
        mqtt_topic="devices/ac1/telemetry",
    )
    db.add(tracker)
    db.commit()

    shipment = Shipment(
        organization_id=org.id,
        tracker_id=tracker.id,
        status=ShipmentStatus.ACTIVE,
        minimum_temperature=-20.0,
        maximum_temperature=-15.0,
        grace_readings=2,
    )
    db.add(shipment)
    db.commit()

    now = datetime.now(timezone.utc)
    reading = Telemetry(
        organization_id=org.id,
        shipment_id=shipment.id,
        tracker_id=tracker.id,
        temperature=-18.5,
        humidity=45.2,
        battery=94.0,
        door_status=False,
        latitude=12.9716,
        longitude=77.5946,
        timestamp=now,
    )
    db.add(reading)
    db.commit()

    saved_reading = db.scalar(select(Telemetry).where(Telemetry.id == reading.id))
    assert saved_reading is not None
    assert saved_reading.organization_id == org.id
    assert saved_reading.shipment_id == shipment.id
    assert saved_reading.tracker_id == tracker.id
    assert saved_reading.temperature == -18.5
    assert saved_reading.humidity == 45.2
    assert saved_reading.battery == 94.0
    assert saved_reading.door_status is False
    assert saved_reading.latitude == 12.9716
    assert saved_reading.longitude == 77.5946


def test_create_alert_record(db: Session):
    """Test 6: Alert references organization, shipment, and tracker."""
    org = Organization(name=f"ApexHealth-{uuid.uuid4().hex[:8]}")
    db.add(org)
    db.commit()

    tracker = Tracker(
        organization_id=org.id,
        name="ApexSensor-99",
        mqtt_topic="devices/apex-99/telemetry",
    )
    db.add(tracker)
    db.commit()

    shipment = Shipment(
        organization_id=org.id,
        tracker_id=tracker.id,
        status=ShipmentStatus.ACTIVE,
        minimum_temperature=2.0,
        maximum_temperature=8.0,
        grace_readings=1,
    )
    db.add(shipment)
    db.commit()

    now = datetime.now(timezone.utc)
    alert = Alert(
        organization_id=org.id,
        shipment_id=shipment.id,
        tracker_id=tracker.id,
        type=AlertType.TEMPERATURE_BREACH,
        message="Temperature reached 9.4C exceeding 8.0C maximum threshold.",
        triggered_at=now,
        resolved_at=None,
    )
    db.add(alert)
    db.commit()

    saved_alert = db.scalar(select(Alert).where(Alert.id == alert.id))
    assert saved_alert is not None
    assert saved_alert.organization_id == org.id
    assert saved_alert.shipment_id == shipment.id
    assert saved_alert.tracker_id == tracker.id
    assert saved_alert.type == AlertType.TEMPERATURE_BREACH
    assert "exceeding" in saved_alert.message
    assert saved_alert.resolved_at is None


def test_foreign_key_enforcement(db: Session):
    """Test 7: Foreign key enforcement prevents invalid references."""
    non_existent_id = uuid.uuid4()
    tracker = Tracker(
        organization_id=non_existent_id,
        name="Ghost-Tracker",
        mqtt_topic="devices/ghost/telemetry",
    )
    db.add(tracker)
    with pytest.raises(IntegrityError):
        db.commit()


def test_protect_telemetry_from_deletion(db: Session):
    """Test 8: RESTRICT constraint protects historical shipments with telemetry from accidental deletion."""
    org = Organization(name=f"SecureCold-{uuid.uuid4().hex[:8]}")
    db.add(org)
    db.commit()

    tracker = Tracker(
        organization_id=org.id,
        name="Tracker-Restricted",
        mqtt_topic="devices/res/telemetry",
    )
    db.add(tracker)
    db.commit()

    shipment = Shipment(
        organization_id=org.id,
        tracker_id=tracker.id,
        minimum_temperature=2.0,
        maximum_temperature=8.0,
    )
    db.add(shipment)
    db.commit()

    reading = Telemetry(
        organization_id=org.id,
        shipment_id=shipment.id,
        tracker_id=tracker.id,
        temperature=4.0,
        humidity=50.0,
        battery=88.0,
        door_status=False,
        latitude=13.0,
        longitude=80.0,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(reading)
    db.commit()

    # Attempting to delete shipment should fail because telemetry references it with ondelete=RESTRICT
    db.delete(shipment)
    with pytest.raises(IntegrityError):
        db.commit()


# ==============================================================================
# Cross-Tenant Integrity Tests (Composite Foreign Key Verification)
# ==============================================================================

def test_cross_tenant_shipment_tracker_rejected(db: Session):
    """TEST 1: Shipment cannot reference a tracker belonging to a different organization."""
    org_a = Organization(name=f"Org-A-{uuid.uuid4().hex[:8]}")
    org_b = Organization(name=f"Org-B-{uuid.uuid4().hex[:8]}")
    db.add_all([org_a, org_b])
    db.commit()

    tracker_a = Tracker(
        organization_id=org_a.id,
        name="Tracker-Org-A",
        mqtt_topic="devices/tracker-a/telemetry",
    )
    db.add(tracker_a)
    db.commit()

    # Attempt to create Shipment in Org B referencing Tracker in Org A
    cross_tenant_shipment = Shipment(
        organization_id=org_b.id,
        tracker_id=tracker_a.id,
        minimum_temperature=2.0,
        maximum_temperature=8.0,
    )
    db.add(cross_tenant_shipment)
    with pytest.raises(IntegrityError):
        db.commit()


def test_cross_tenant_telemetry_shipment_rejected(db: Session):
    """TEST 2: Telemetry cannot reference a shipment belonging to a different organization."""
    org_a = Organization(name=f"Org-A-{uuid.uuid4().hex[:8]}")
    org_b = Organization(name=f"Org-B-{uuid.uuid4().hex[:8]}")
    db.add_all([org_a, org_b])
    db.commit()

    tracker_a = Tracker(
        organization_id=org_a.id,
        name="Tracker-Org-A",
        mqtt_topic="devices/tracker-a/telemetry",
    )
    db.add(tracker_a)
    db.commit()

    shipment_a = Shipment(
        organization_id=org_a.id,
        tracker_id=tracker_a.id,
        minimum_temperature=2.0,
        maximum_temperature=8.0,
    )
    db.add(shipment_a)
    db.commit()

    # Attempt to create Telemetry in Org B referencing Shipment in Org A
    cross_telemetry = Telemetry(
        organization_id=org_b.id,
        shipment_id=shipment_a.id,
        tracker_id=tracker_a.id,
        temperature=4.5,
        humidity=60.0,
        battery=90.0,
        door_status=False,
        latitude=12.9,
        longitude=77.6,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(cross_telemetry)
    with pytest.raises(IntegrityError):
        db.commit()


def test_cross_tenant_telemetry_tracker_rejected(db: Session):
    """TEST 3: Telemetry cannot reference a tracker belonging to a different organization."""
    org_a = Organization(name=f"Org-A-{uuid.uuid4().hex[:8]}")
    org_b = Organization(name=f"Org-B-{uuid.uuid4().hex[:8]}")
    db.add_all([org_a, org_b])
    db.commit()

    tracker_a = Tracker(
        organization_id=org_a.id,
        name="Tracker-Org-A",
        mqtt_topic="devices/tracker-a/telemetry",
    )
    tracker_b = Tracker(
        organization_id=org_b.id,
        name="Tracker-Org-B",
        mqtt_topic="devices/tracker-b/telemetry",
    )
    db.add_all([tracker_a, tracker_b])
    db.commit()

    shipment_b = Shipment(
        organization_id=org_b.id,
        tracker_id=tracker_b.id,
        minimum_temperature=2.0,
        maximum_temperature=8.0,
    )
    db.add(shipment_b)
    db.commit()

    # Attempt to create Telemetry in Org B referencing Shipment in Org B but Tracker from Org A
    cross_telemetry = Telemetry(
        organization_id=org_b.id,
        shipment_id=shipment_b.id,
        tracker_id=tracker_a.id,
        temperature=4.5,
        humidity=60.0,
        battery=90.0,
        door_status=False,
        latitude=12.9,
        longitude=77.6,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(cross_telemetry)
    with pytest.raises(IntegrityError):
        db.commit()


def test_cross_tenant_alert_shipment_rejected(db: Session):
    """TEST 4: Alert cannot reference a shipment belonging to a different organization."""
    org_a = Organization(name=f"Org-A-{uuid.uuid4().hex[:8]}")
    org_b = Organization(name=f"Org-B-{uuid.uuid4().hex[:8]}")
    db.add_all([org_a, org_b])
    db.commit()

    tracker_a = Tracker(
        organization_id=org_a.id,
        name="Tracker-Org-A",
        mqtt_topic="devices/tracker-a/telemetry",
    )
    db.add(tracker_a)
    db.commit()

    shipment_a = Shipment(
        organization_id=org_a.id,
        tracker_id=tracker_a.id,
        minimum_temperature=2.0,
        maximum_temperature=8.0,
    )
    db.add(shipment_a)
    db.commit()

    # Attempt to create Alert in Org B referencing Shipment in Org A
    cross_alert = Alert(
        organization_id=org_b.id,
        shipment_id=shipment_a.id,
        tracker_id=tracker_a.id,
        type=AlertType.TEMPERATURE_BREACH,
        message="Cross-tenant breach attempt",
        triggered_at=datetime.now(timezone.utc),
    )
    db.add(cross_alert)
    with pytest.raises(IntegrityError):
        db.commit()


def test_cross_tenant_alert_tracker_rejected(db: Session):
    """TEST 5: Alert cannot reference a tracker belonging to a different organization."""
    org_a = Organization(name=f"Org-A-{uuid.uuid4().hex[:8]}")
    org_b = Organization(name=f"Org-B-{uuid.uuid4().hex[:8]}")
    db.add_all([org_a, org_b])
    db.commit()

    tracker_a = Tracker(
        organization_id=org_a.id,
        name="Tracker-Org-A",
        mqtt_topic="devices/tracker-a/telemetry",
    )
    tracker_b = Tracker(
        organization_id=org_b.id,
        name="Tracker-Org-B",
        mqtt_topic="devices/tracker-b/telemetry",
    )
    db.add_all([tracker_a, tracker_b])
    db.commit()

    shipment_b = Shipment(
        organization_id=org_b.id,
        tracker_id=tracker_b.id,
        minimum_temperature=2.0,
        maximum_temperature=8.0,
    )
    db.add(shipment_b)
    db.commit()

    # Attempt to create Alert in Org B referencing Shipment in Org B but Tracker from Org A
    cross_alert = Alert(
        organization_id=org_b.id,
        shipment_id=shipment_b.id,
        tracker_id=tracker_a.id,
        type=AlertType.TEMPERATURE_BREACH,
        message="Cross-tenant tracker alert attempt",
        triggered_at=datetime.now(timezone.utc),
    )
    db.add(cross_alert)
    with pytest.raises(IntegrityError):
        db.commit()


def test_valid_same_organization_relationship_succeeds(db: Session):
    """Verify that all relationships within the same organization persist smoothly."""
    org = Organization(name=f"ValidTenant-{uuid.uuid4().hex[:8]}")
    db.add(org)
    db.commit()

    tracker = Tracker(
        organization_id=org.id,
        name="ValidTracker",
        mqtt_topic="devices/valid/telemetry",
    )
    db.add(tracker)
    db.commit()

    shipment = Shipment(
        organization_id=org.id,
        tracker_id=tracker.id,
        minimum_temperature=2.0,
        maximum_temperature=8.0,
    )
    db.add(shipment)
    db.commit()

    telemetry = Telemetry(
        organization_id=org.id,
        shipment_id=shipment.id,
        tracker_id=tracker.id,
        temperature=5.0,
        humidity=55.0,
        battery=92.0,
        door_status=False,
        latitude=12.95,
        longitude=77.58,
        timestamp=datetime.now(timezone.utc),
    )
    alert = Alert(
        organization_id=org.id,
        shipment_id=shipment.id,
        tracker_id=tracker.id,
        type=AlertType.DOOR_OPEN,
        message="Door opened during valid shipment",
        triggered_at=datetime.now(timezone.utc),
    )
    db.add_all([telemetry, alert])
    db.commit()

    assert telemetry.id is not None
    assert alert.id is not None
    assert telemetry.shipment.id == shipment.id
    assert telemetry.tracker.id == tracker.id
    assert alert.shipment.id == shipment.id
    assert alert.tracker.id == tracker.id
