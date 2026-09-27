"""Production and development database seed script for SWASEMI Cold-Chain Monitoring Platform.

Creates:
1. SUPER_ADMIN user (admin@swasemi.com / Password@123)
2. Tenant Organization (Apex Pharma Global)
3. Standard USER (operator@apexpharma.com / Password@123)
4. 4 Hardware Trackers (matching simulator/config.py UUIDs and topics):
   - Apex Cold-Box 101 (73908884-4df0-4afb-965f-2815e6d11adc)
   - Medical_UnitA (b140093e-b69b-4ab5-92e3-1a97e6cd6a62)
   - Medical_UnitB (05d3d094-58c7-41ff-b57e-a772948539d6)
   - Apex Cold-Box 102 (52a2dc8c-c613-4546-836d-6c64e49a15aa)
5. Active Shipments for live streaming & compliance monitoring
6. Baseline telemetry trail for initial UI presentation

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

        # 2. Sample Tenant Organization (Apex Pharma Global)
        org = db.query(Organization).filter_by(name="Apex Pharma Global").first()
        if not org:
            org = Organization(
                id=uuid.UUID("36817a3b-0bfe-4577-a647-da8325232448"),
                name="Apex Pharma Global",
            )
            db.add(org)
            db.flush()
            print(f"Created Organization: {org.name} (ID: {org.id})")
        else:
            print(f"Organization already exists: {org.name} (ID: {org.id})")

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

        # 4. Hardware Trackers (at least 4 trackers matching simulator UUIDs/topics)
        trackers_map = {}
        for t_cfg in SEED_TRACKERS:
            tracker = db.query(Tracker).filter_by(id=t_cfg["id"]).first()
            if not tracker:
                # Handle potential legacy tracker with same name but different ID
                legacy_trackers = db.query(Tracker).filter(
                    Tracker.id != t_cfg["id"],
                    Tracker.name == t_cfg["name"],
                ).all()
                for lt in legacy_trackers:
                    lt.name = f"{lt.name} (Legacy)"
                    print(f"Renamed legacy tracker to avoid name collision: {lt.name} ({lt.id})")

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
                # Synchronize properties to ensure alignment with simulator
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

            trackers_map[str(t_cfg["id"])] = tracker

        # 5. Active Shipments for Trackers
        for t_cfg in SEED_TRACKERS:
            if not t_cfg["has_active_shipment"]:
                continue

            t_id = t_cfg["id"]
            active_shipment = db.query(Shipment).filter_by(
                tracker_id=t_id,
                status=ShipmentStatus.ACTIVE,
            ).first()

            if not active_shipment:
                # Check if any existing shipment is tied to this tracker
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

        # 6. Sample Initial Telemetry for Apex Cold-Box 101 (Tracker 1)
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

        db.commit()
        print("Database seeding completed successfully!")
    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
