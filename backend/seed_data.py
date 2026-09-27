"""Seed script for development environment.

Creates:
1. SUPER_ADMIN user (admin@swasemi.com / Password@123)
2. Tenant Organization (Apex Pharma Global)
3. Standard USER (operator@apexpharma.com / Password@123)
4. Sample Trackers (Apex Tracker Alpha & Beta)
5. Sample Active Shipment
"""

import uuid
from datetime import datetime, timezone
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.models.tracker import Tracker, TrackerStatus
from app.models.shipment import Shipment, ShipmentStatus


def seed_database():
    db = SessionLocal()
    try:
        # 1. Super Admin (organization_id is None)
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

        # 2. Sample Organization
        org = db.query(Organization).filter_by(name="Apex Pharma Global").first()
        if not org:
            org = Organization(
                id=uuid.uuid4(),
                name="Apex Pharma Global",
            )
            db.add(org)
            db.flush()
            print(f"Created Organization: {org.name} (ID: {org.id})")
        else:
            print(f"Organization already exists: {org.name}")

        # 3. Standard USER
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

        # 4. Sample Trackers
        tracker1 = db.query(Tracker).filter_by(mqtt_topic="swasemi/trackers/apex-001").first()
        if not tracker1:
            tracker1 = Tracker(
                id=uuid.uuid4(),
                organization_id=org.id,
                name="Apex Cold-Box 101",
                mqtt_topic="swasemi/trackers/apex-001",
                status=TrackerStatus.ONLINE,
                last_seen=datetime.now(timezone.utc),
            )
            db.add(tracker1)
            db.flush()
            print("Created Tracker: Apex Cold-Box 101")

        tracker2 = db.query(Tracker).filter_by(mqtt_topic="swasemi/trackers/apex-002").first()
        if not tracker2:
            tracker2 = Tracker(
                id=uuid.uuid4(),
                organization_id=org.id,
                name="Apex Cold-Box 102",
                mqtt_topic="swasemi/trackers/apex-002",
                status=TrackerStatus.OFFLINE,
                last_seen=None,
            )
            db.add(tracker2)
            db.flush()
            print("Created Tracker: Apex Cold-Box 102")

        # 5. Sample Shipment for Tracker 1
        if tracker1:
            shipment = db.query(Shipment).filter_by(tracker_id=tracker1.id).first()
            if not shipment:
                shipment = Shipment(
                    id=uuid.uuid4(),
                    organization_id=org.id,
                    tracker_id=tracker1.id,
                    status=ShipmentStatus.ACTIVE,
                    started_at=datetime.now(timezone.utc),
                    minimum_temperature=2.0,
                    maximum_temperature=8.0,
                    grace_readings=3,
                    breach_active=False,
                )
                db.add(shipment)
                db.flush()
                print("Created ACTIVE Shipment for Tracker 1 (2°C - 8°C)")

            from app.models.telemetry import Telemetry
            from datetime import timedelta
            telemetry_count = db.query(Telemetry).filter_by(shipment_id=shipment.id).count()
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
                        shipment_id=shipment.id,
                        tracker_id=tracker1.id,
                        temperature=temp,
                        humidity=hum,
                        battery=bat,
                        door_status=door,
                        latitude=lat,
                        longitude=lon,
                        timestamp=ts,
                    )
                    db.add(t)
                print("Created 4 sample telemetry data points with GPS trail.")

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
