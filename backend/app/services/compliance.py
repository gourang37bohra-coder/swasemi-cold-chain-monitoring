"""Temperature compliance and breach alert evaluation service."""

from datetime import datetime, timezone
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.alert import Alert, AlertType
from app.models.shipment import Shipment
from app.models.telemetry import Telemetry
from app.models.tracker import Tracker
from app.realtime.events import publish_alert_event
from app.services.email_service import email_service

logger = logging.getLogger("coldchain.compliance")


def evaluate_temperature_compliance(
    db: Session,
    shipment: Shipment,
    tracker: Tracker,
    telemetry: Telemetry,
) -> Optional[Alert]:
    """Evaluate temperature compliance against shipment tolerance profile.

    Business Rules:
      1. Violation check: temperature < minimum_temperature OR temperature > maximum_temperature.
      2. If violating:
         - Increment consecutive_violations.
         - If consecutive_violations >= grace_readings:
           - If breach_active is False (NEW BREACH):
             - Set breach_active = True.
             - Create Alert record in PostgreSQL.
             - Commit transaction & refresh alert.
             - Publish alert to Redis Pub/Sub for real-time WebSocket distribution.
             - Dispatch SMTP alert email.
             - Return created Alert.
           - Else (CONTINUOUS BREACH ALREADY ACTIVE):
             - Persist updated consecutive_violations count.
             - DO NOT send duplicate email.
             - DO NOT create duplicate Alert record.
      3. If in-range (compliance restored):
         - If shipment had violations or breach_active was True:
           - Reset consecutive_violations to 0.
           - Reset breach_active to False.
           - Commit updated shipment state to PostgreSQL.
           - Log restoration of thermal compliance.
    """
    temp = telemetry.temperature
    is_violation = (temp < shipment.minimum_temperature) or (temp > shipment.maximum_temperature)

    if is_violation:
        shipment.consecutive_violations += 1
        logger.info(
            "Temperature violation on shipment %s (tracker %s): %.2fC outside [%.1fC, %.1fC]. "
            "Consecutive count: %d / Grace: %d",
            shipment.id,
            tracker.id,
            temp,
            shipment.minimum_temperature,
            shipment.maximum_temperature,
            shipment.consecutive_violations,
            shipment.grace_readings,
        )

        if shipment.consecutive_violations >= shipment.grace_readings:
            if not shipment.breach_active:
                # ── NEW BREACH CONFIRMED ─────────────────────────────
                shipment.breach_active = True
                alert = Alert(
                    organization_id=shipment.organization_id,
                    shipment_id=shipment.id,
                    tracker_id=tracker.id,
                    type=AlertType.TEMPERATURE_BREACH,
                    message=(
                        f"Temperature breach detected: reading {temp:.2f}°C is outside "
                        f"permitted range ({shipment.minimum_temperature:.1f}°C to {shipment.maximum_temperature:.1f}°C) "
                        f"after {shipment.consecutive_violations} consecutive violating reading(s)."
                    ),
                    temperature=temp,
                    triggered_at=telemetry.timestamp,
                    resolved_at=None,
                )
                db.add(alert)
                db.commit()
                db.refresh(alert)
                logger.warning(
                    "BREACH ALERT CREATED: id=%s shipment=%s tracker=%s temp=%.2fC violations=%d",
                    alert.id,
                    shipment.id,
                    tracker.id,
                    temp,
                    shipment.consecutive_violations,
                )

                # Real-time WebSocket delivery via Redis Pub/Sub
                publish_alert_event(alert)

                # SMTP Email delivery (failure never rolls back DB)
                email_service.send_breach_alert(
                    alert=alert,
                    shipment=shipment,
                    tracker=tracker,
                    telemetry=telemetry,
                )

                return alert
            else:
                # ── CONTINUOUS BREACH ALREADY ACTIVE ─────────────────
                # Prevent repeated alert records and repeated emails
                db.commit()
                logger.debug(
                    "Shipment %s already has breach_active=True. Duplicate email/alert suppressed.",
                    shipment.id,
                )
                return None
        else:
            # Within grace window; commit violation counter
            db.commit()
            return None

    else:
        # In range: reset continuous breach state if previously set
        if shipment.consecutive_violations > 0 or shipment.breach_active:
            logger.info(
                "Temperature restored to safe range (%.2fC) for shipment %s. Resetting breach state.",
                temp,
                shipment.id,
            )
            shipment.consecutive_violations = 0
            shipment.breach_active = False
            db.commit()

        return None
