"""Email delivery service for temperature breach notifications."""

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging
import smtplib
from typing import Optional

from app.core.config import settings
from app.models.alert import Alert
from app.models.shipment import Shipment
from app.models.telemetry import Telemetry
from app.models.tracker import Tracker

logger = logging.getLogger("coldchain.email")


class EmailService:
    """Manages SMTP connection and alert email formatting."""

    @classmethod
    def send_breach_alert(
        cls,
        alert: Alert,
        shipment: Shipment,
        tracker: Tracker,
        telemetry: Telemetry,
        recipient_override: Optional[str] = None,
    ) -> bool:
        """Send a temperature breach alert email via configured SMTP server.

        Guarantees:
          - Never throws an unhandled exception to caller.
          - Never blocks or rollbacks database persistence.
          - Logs failure details with clear diagnostic message.
        """
        if not settings.EMAIL_ENABLED:
            logger.info("Email alerts disabled via configuration (EMAIL_ENABLED=False). Skipping SMTP dispatch.")
            return True

        recipient = recipient_override or settings.ALERT_EMAIL_TO
        subject = f"[SWASEMI ALERT] Temperature Breach - Tracker '{tracker.name}' (Shipment {str(shipment.id)[:8]})"

        # Plaintext body formatting
        body_text = (
            "==========================================================\n"
            "         SWASEMI COLD-CHAIN TEMPERATURE ALERT            \n"
            "==========================================================\n\n"
            f"Alert Type:               {alert.type.value if hasattr(alert.type, 'value') else alert.type}\n"
            f"Organization ID:          {shipment.organization_id}\n"
            f"Shipment ID:              {shipment.id}\n"
            f"Tracker:                  {tracker.name} ({tracker.id})\n\n"
            f"Observed Temperature:     {telemetry.temperature:.2f} °C\n"
            f"Allowed Range:            {shipment.minimum_temperature:.1f} °C to {shipment.maximum_temperature:.1f} °C\n"
            f"Grace Threshold:          {shipment.grace_readings} consecutive reading(s)\n"
            f"Consecutive Violations:   {shipment.consecutive_violations}\n"
            f"Time of Breach (UTC):     {telemetry.timestamp.isoformat()}\n"
            f"GPS Coordinates:          {telemetry.latitude:.4f}, {telemetry.longitude:.4f}\n\n"
            f"Alert Message:\n{alert.message}\n\n"
            "Immediate action is recommended to inspect cooling units and verify cargo integrity.\n"
            "==========================================================\n"
        )

        msg = MIMEMultipart()
        msg["From"] = settings.SMTP_FROM
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(body_text, "plain", "utf-8"))

        try:
            logger.info(
                "Connecting to SMTP server at %s:%s to send alert for shipment %s...",
                settings.SMTP_HOST,
                settings.SMTP_PORT,
                shipment.id,
            )
            # Use standard smtplib with a 3.0s timeout
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=3.0) as server:
                if settings.SMTP_TLS:
                    server.starttls()
                if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                    server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.send_message(msg)

            logger.info(
                "Successfully delivered breach alert email to %s for shipment %s.",
                recipient,
                shipment.id,
            )
            return True

        except Exception as exc:
            logger.warning(
                "Failed to send breach alert email via %s:%s: %s (%s). Ingestion unaffected.",
                settings.SMTP_HOST,
                settings.SMTP_PORT,
                type(exc).__name__,
                exc,
            )
            return False


email_service = EmailService()
