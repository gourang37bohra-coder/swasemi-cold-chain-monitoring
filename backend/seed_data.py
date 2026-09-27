"""Production and development database seed script for SWASEMI Cold-Chain Monitoring Platform.

Creates:
1. SUPER_ADMIN user (admin@swasemi.com / Password@123)
2. Tenant Organization (Apex Pharma Global)
3. Standard USER (operator@apexpharma.com / Password@123)
4. Exactly 4 Hardware Trackers (matching simulator/config.py UUIDs and topics):
   - Apex Cold-Box 101 (73908884-4df0-4afb-965f-2815e6d11adc)
   - Medical_UnitA (b140093e-b69b-4ab5-92e3-1a97e6cd6a62)
   - Medical_UnitB (05d3d094-58c7-41ff-b57e-a772948539d6)
   - Apex Cold-Box 102 (52a2dc8c-c613-4546-836d-6c64e49a15aa)
5. Idempotent migration/cleanup of legacy tracker UUIDs (re-homing foreign keys).
6. Active Shipments for live streaming & compliance monitoring
7. Baseline telemetry trail for initial UI presentation

This script is 100% idempotent: running it multiple times will not duplicate
organizations, users, trackers, shipments, or telemetry records.
"""

import uuid
from datetime import datetime, timedelta, timezone

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.models.tracker import Tracker, TrackerStatus
from app.models.shipment import Shipment, ShipmentStatus
from app.models.telemetry import Telemetry
from app.models.alert import Alert



# Pre-configured Hardware Trackers aligned with simulator/config.py
SEED_TRACKERS = [
    {
        "id": uuid.UUID("73908884-4df0-4afb-965f-2815e6d11adc"),
        "name": "Apex Cold-Box 101",
        "mqtt_topic": "coldchain/trackers/73908884-4df0-4afb-965f-2815e6d11adc/telemetry",
        "status": TrackerStatus.ONLINE,
        "default_temp_min": 2.0,
        "default_temp_max": 8.0,
        "has_active_shipment": True,
    },
    {
        "id": uuid.UUID("b140093e-b69b-4ab5-92e3-1a97e6cd6a62"),
        "name": "Medical_UnitA",
        "mqtt_topic": "coldchain/trackers/b140093e-b69b-4ab5-92e3-1a97e6cd6a62/telemetry",
        "status": TrackerStatus.ONLINE,
        "default_temp_min": 1.0,
        "default_temp_max": 3.0,
        "has_active_shipment": True,
    },
    {
        "id": uuid.UUID("05d3d094-58c7-41ff-b57e-a772948539d6"),
        "name": "Medical_UnitB",
        "mqtt_topic": "coldchain/trackers/05d3d094-58c7-41ff-b57e-a772948539d6/telemetry",
        "status": TrackerStatus.ONLINE,
        "default_temp_min": 4.0,
        "default_temp_max": 8.0,
        "has_active_shipment": True,
    },
    {
        "id": uuid.UUID("52a2dc8c-c613-4546-836d-6c64e49a15aa"),
        "name": "Apex Cold-Box 102",
        "mqtt_topic": "coldchain/trackers/52a2dc8c-c613-4546-836d-6c64e49a15aa/telemetry",
        "status": TrackerStatus.OFFLINE,
        "default_temp_min": 2.0,
        "default_temp_max": 8.0,
        "has_active_shipment": False,  # Reserved for gating demo
    },
]

# Legacy trackers identified strictly by exact UUID and mapped to simulator trackers
LEGACY_TRACKER_MAPPINGS = [
    {
        "legacy_id": uuid.UUID("b25afd5e-d3bf-43cd-b498-966def3638de"),
        "target_id": uuid.UUID("73908884-4df0-4afb-965f-2815e6d11adc"),
        "name": "Apex Cold-Box 101",
    },
    {
        "legacy_id": uuid.UUID("76167925-469b-4592-a031-d89979cbd1f9"),
        "target_id": uuid.UUID("52a2dc8c-c613-4546-836d-6c64e49a15aa"),
        "name": "Apex Cold-Box 102",
    },
]


def cleanup_legacy_trackers(db: SessionLocal, org: Organization) -> None:
    """Safely migrate historical shipments, telemetry, and alerts from legacy trackers
    to standard simulator trackers, then remove the legacy tracker records.

    Safety requirements:
    1. Transactional: runs within the caller's transaction; failure triggers rollback.
    2. Identifies legacy trackers ONLY by exact UUIDs (never by name).
    3. Scoped strictly to the target organization (using org.id dynamically).
    4. Re-homes shipments before telemetry/alerts to maintain foreign-key graph.
    5. Preserves all telemetry/alert/shipment fields and timestamps intact (only tracker_id changes).
    6. If a legacy shipment is ACTIVE and the target tracker already has an ACTIVE shipment,
       marks only the duplicate legacy shipment COMPLETED (ended_at = now). Does NOT modify target shipment.
    7. Verifies zero remaining foreign-key references before deleting legacy tracker rows.
    """
    assert org is not None and org.id is not None, "A valid organization with a populated ID is required for legacy cleanup."
    cleanup_time = datetime.now(timezone.utc)

    for mapping in LEGACY_TRACKER_MAPPINGS:
        legacy_id = mapping["legacy_id"]
        target_id = mapping["target_id"]

        legacy_tracker = db.query(Tracker).filter(Tracker.id == legacy_id).first()

        if not legacy_tracker:
            print(f"Legacy tracker {legacy_id} ({mapping.get('name', 'Unknown')}) not present. Skipping.")
            continue

        if legacy_tracker.organization_id != org.id:
            raise RuntimeError(
                f"Organization mismatch for legacy tracker {legacy_id}: "
                f"expected org {org.id}, found {legacy_tracker.organization_id}. Aborting."
            )

        print(f"Discovered legacy tracker {legacy_id} ({legacy_tracker.name}) for migration -> {target_id}")

        # Ensure target tracker exists before re-homing foreign keys
        target_tracker = db.query(Tracker).filter(
            Tracker.id == target_id,
            Tracker.organization_id == org.id,
        ).first()
        if not target_tracker:
            t_cfg = next(t for t in SEED_TRACKERS if t["id"] == target_id)
            target_tracker = Tracker(
                id=t_cfg["id"],
                organization_id=org.id,
                name=t_cfg["name"],
                mqtt_topic=t_cfg["mqtt_topic"],
                status=t_cfg["status"],
                last_seen=datetime.now(timezone.utc) if t_cfg["status"] == TrackerStatus.ONLINE else None,
            )
            db.add(target_tracker)
            db.flush()
            print(f"Created target tracker {target_tracker.name} ({target_tracker.id}) prior to re-homing.")

        # 1. Re-home shipments
        target_active_shipment = db.query(Shipment).filter(
            Shipment.tracker_id == target_id,
            Shipment.organization_id == org.id,
            Shipment.status == ShipmentStatus.ACTIVE,
        ).first()

        legacy_shipments = db.query(Shipment).filter(
            Shipment.tracker_id == legacy_id,
            Shipment.organization_id == org.id,
        ).all()

        for s in legacy_shipments:
            if s.status == ShipmentStatus.ACTIVE and target_active_shipment is not None and s.id != target_active_shipment.id:
                s.status = ShipmentStatus.COMPLETED
                s.ended_at = cleanup_time
                print(f"Archived duplicate legacy active shipment {s.id} as COMPLETED (ended_at={cleanup_time.isoformat()})")
            s.tracker_id = target_id
            print(f"Re-homed shipment {s.id} to target tracker {target_id}")

        db.flush()

        # 2. Re-home telemetry (preserving all fields/timestamps, only updating tracker_id)
        telem_count = db.query(Telemetry).filter(
            Telemetry.tracker_id == legacy_id,
            Telemetry.organization_id == org.id,
        ).update({"tracker_id": target_id}, synchronize_session=False)
        if telem_count > 0:
            print(f"Re-homed {telem_count} telemetry record(s) from {legacy_id} to {target_id}")
        db.flush()

        # 3. Re-home alerts (preserving all fields/timestamps, only updating tracker_id)
        alert_count = db.query(Alert).filter(
            Alert.tracker_id == legacy_id,
            Alert.organization_id == org.id,
        ).update({"tracker_id": target_id}, synchronize_session=False)
        if alert_count > 0:
            print(f"Re-homed {alert_count} alert(s) from {legacy_id} to {target_id}")
        db.flush()

        # 4. Verify zero remaining references before deleting legacy tracker
        rem_shipments = db.query(Shipment).filter_by(tracker_id=legacy_id).count()
        rem_telemetry = db.query(Telemetry).filter_by(tracker_id=legacy_id).count()
        rem_alerts = db.query(Alert).filter_by(tracker_id=legacy_id).count()

        if rem_shipments == 0 and rem_telemetry == 0 and rem_alerts == 0:
            db.delete(legacy_tracker)
            db.flush()
            print(f"Safely deleted legacy tracker {legacy_id} (0 remaining references).")
        else:
            raise RuntimeError(
                f"Aborting deletion of legacy tracker {legacy_id}: still referenced by "
                f"{rem_shipments} shipment(s), {rem_telemetry} telemetry row(s), {rem_alerts} alert(s)."
            )


def seed_database():
    db = SessionLocal()
    try:
        # 1. Super Admin (platform-wide visibility, organization_id is None)
        admin = db.query(User).filter_by(email="admin@swasemi.com").first()
        if not admin:
            admin = User(
                id=uuid.uuid4(),
                organization_id=None,
                email="admin@swasemi.com",
                password_hash=hash_password("Password@123"),
                role=UserRole.SUPER_ADMIN,
            )
            db.add(admin)
            print("Created SUPER_ADMIN: admin@swasemi.com / Password@123")
        else:
            print("SUPER_ADMIN already exists: admin@swasemi.com")

        # 2. Tenant Organization (Apex Pharma Global)
        matching_orgs = db.query(Organization).filter_by(name="Apex Pharma Global").all()
        if len(matching_orgs) > 1:
            raise RuntimeError(
                f"Ambiguous state: found {len(matching_orgs)} organizations named 'Apex Pharma Global'. Aborting."
            )
        elif len(matching_orgs) == 1:
            org = matching_orgs[0]
            print(f"Located existing organization: {org.name} (ID: {org.id})")
        else:
            org = Organization(
                name="Apex Pharma Global",
            )
            db.add(org)
            db.flush()
            print(f"Created Organization: {org.name} (ID: {org.id})")

        # 3. Standard Tenant Operator USER
        user = db.query(User).filter_by(email="operator@apexpharma.com").first()
        if not user:
            user = User(
                id=uuid.uuid4(),
                organization_id=org.id,
                email="operator@apexpharma.com",
                password_hash=hash_password("Password@123"),
                role=UserRole.USER,
            )
            db.add(user)
            print("Created USER: operator@apexpharma.com / Password@123")
        else:
            print("USER already exists: operator@apexpharma.com")

        # 4. Clean up and migrate any legacy trackers prior to standard tracker synchronization
        cleanup_legacy_trackers(db, org)

        # 5. Hardware Trackers (exactly 4 trackers matching simulator UUIDs/topics)
        for t_cfg in SEED_TRACKERS:
            tracker = db.query(Tracker).filter_by(id=t_cfg["id"]).first()
            if not tracker:
                tracker = Tracker(
                    id=t_cfg["id"],
                    organization_id=org.id,
                    name=t_cfg["name"],
                    mqtt_topic=t_cfg["mqtt_topic"],
                    status=t_cfg["status"],
                    last_seen=datetime.now(timezone.utc) if t_cfg["status"] == TrackerStatus.ONLINE else None,
                )
                db.add(tracker)
                db.flush()
                print(f"Created Tracker: {tracker.name} ({tracker.id}) -> {tracker.mqtt_topic}")
            else:
                updated = False
                if tracker.name != t_cfg["name"]:
                    tracker.name = t_cfg["name"]
                    updated = True
                if tracker.mqtt_topic != t_cfg["mqtt_topic"]:
                    tracker.mqtt_topic = t_cfg["mqtt_topic"]
                    updated = True
                if tracker.organization_id != org.id:
                    tracker.organization_id = org.id
                    updated = True
                if updated:
                    db.flush()
                    print(f"Updated Tracker: {tracker.name} ({tracker.id}) -> {tracker.mqtt_topic}")
                else:
                    print(f"Tracker already exists: {tracker.name} ({tracker.id})")

        # 6. Active Shipments for Trackers
        for t_cfg in SEED_TRACKERS:
            if not t_cfg["has_active_shipment"]:
                continue

            t_id = t_cfg["id"]
            active_shipment = db.query(Shipment).filter_by(
                tracker_id=t_id,
                status=ShipmentStatus.ACTIVE,
            ).first()

            if not active_shipment:
                existing_shipment = db.query(Shipment).filter_by(tracker_id=t_id).first()
                if not existing_shipment:
                    active_shipment = Shipment(
                        id=uuid.uuid4(),
                        organization_id=org.id,
                        tracker_id=t_id,
                        status=ShipmentStatus.ACTIVE,
                        started_at=datetime.now(timezone.utc),
                        minimum_temperature=t_cfg["default_temp_min"],
                        maximum_temperature=t_cfg["default_temp_max"],
                        grace_readings=3,
                        consecutive_violations=0,
                        breach_active=False,
                    )
                    db.add(active_shipment)
                    db.flush()
                    print(
                        f"Created ACTIVE Shipment for {t_cfg['name']} "
                        f"({t_cfg['default_temp_min']}°C - {t_cfg['default_temp_max']}°C, grace: 3)"
                    )
                else:
                    print(f"Shipment already exists for {t_cfg['name']} (Status: {existing_shipment.status.value})")
            else:
                print(f"ACTIVE Shipment already exists for {t_cfg['name']} (ID: {active_shipment.id})")

        # 7. Sample Initial Telemetry for Apex Cold-Box 101 (Tracker 1)
        tracker1_id = uuid.UUID("73908884-4df0-4afb-965f-2815e6d11adc")
        shipment1 = db.query(Shipment).filter_by(
            tracker_id=tracker1_id,
            status=ShipmentStatus.ACTIVE,
        ).first()

        if shipment1:
            telemetry_count = db.query(Telemetry).filter_by(shipment_id=shipment1.id).count()
            if telemetry_count == 0:
                base_time = datetime.now(timezone.utc) - timedelta(hours=3)
                points = [
                    (4.2, 55.0, 98.0, False, 19.0760, 72.8777, base_time),
                    (4.5, 54.0, 95.0, False, 19.0825, 72.8850, base_time + timedelta(hours=1)),
                    (4.8, 53.5, 92.0, False, 19.1136, 72.8697, base_time + timedelta(hours=2)),
                    (5.1, 52.0, 89.0, False, 19.1670, 72.9320, base_time + timedelta(hours=3)),
                ]
                for temp, hum, bat, door, lat, lon, ts in points:
                    t = Telemetry(
                        id=uuid.uuid4(),
                        organization_id=org.id,
                        shipment_id=shipment1.id,
                        tracker_id=tracker1_id,
                        temperature=temp,
                        humidity=hum,
                        battery=bat,
                        door_status=door,
                        latitude=lat,
                        longitude=lon,
                        timestamp=ts,
                    )
                    db.add(t)
                print("Created 4 sample telemetry data points with GPS trail for Apex Cold-Box 101.")

        # 8. Post-cleanup verification: exactly 4 expected simulator trackers must exist
        org_trackers = db.query(Tracker).filter_by(organization_id=org.id).all()
        current_tracker_ids = {t.id for t in org_trackers}
        expected_tracker_ids = {t["id"] for t in SEED_TRACKERS}
        assert current_tracker_ids == expected_tracker_ids, (
            f"Tracker verification failed! Found: {current_tracker_ids}, Expected: {expected_tracker_ids}"
        )
        print(f"Verified exactly {len(org_trackers)} expected simulator trackers exist in organization.")

        db.commit()
        print("Database seeding and legacy cleanup completed successfully!")
    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
