"""MQTT Telemetry Consumer client using paho-mqtt."""

import logging
from typing import Optional
import uuid

import paho.mqtt.client as mqtt

from app.core.config import settings
from app.core.database import SessionLocal
from app.services.telemetry_ingestion import ingest_telemetry_payload

logger = logging.getLogger("coldchain.mqtt")


class MQTTTelemetryConsumer:
    """Manages connection, subscription, and message dispatch for MQTT telemetry."""

    def __init__(self) -> None:
        client_id = settings.MQTT_CLIENT_ID or f"coldchain-ingest-{uuid.uuid4().hex[:8]}"
        # Use paho-mqtt CallbackAPIVersion.VERSION2 for compatibility with paho-mqtt 2.x
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
        )

        # Configure authentication if provided
        if settings.MQTT_USERNAME:
            self.client.username_pw_set(
                username=settings.MQTT_USERNAME,
                password=settings.MQTT_PASSWORD,
            )

        # Configure TLS if enabled
        if settings.MQTT_TLS:
            self.client.tls_set()

        # Attach callbacks
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

        self.topic_pattern = f"{settings.MQTT_TOPIC_PREFIX}/+/telemetry"
        self._is_connected = False

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self._is_connected = True
            logger.info("Connected to MQTT broker at %s:%s", settings.MQTT_BROKER_HOST, settings.MQTT_BROKER_PORT)
            client.subscribe([(self.topic_pattern, 0), ("swasemi/trackers/#", 0)])
            logger.info("Subscribed to telemetry topics: %s and swasemi/trackers/#", self.topic_pattern)
        else:
            logger.error("Failed to connect to MQTT broker, return code: %s", rc)

    def _on_disconnect(self, client, userdata, rc, properties=None):
        self._is_connected = False
        logger.warning("Disconnected from MQTT broker (code: %s)", rc)

    def _on_message(self, client, userdata, msg):
        """Dispatches an incoming MQTT message to the ingestion service."""
        logger.debug("Received MQTT message on topic: %s", msg.topic)
        session = SessionLocal()
        try:
            result = ingest_telemetry_payload(
                db=session,
                payload_data=msg.payload,
                topic=msg.topic,
            )
            logger.debug("Ingestion outcome for topic %s: %s - %s", msg.topic, result.status, result.message)
        except Exception as exc:
            logger.error("Unexpected error handling MQTT message on %s: %s", msg.topic, type(exc).__name__)
        finally:
            session.close()

    def start(self) -> None:
        """Connect and start background network loop."""
        try:
            logger.info("Connecting to MQTT broker %s:%s...", settings.MQTT_BROKER_HOST, settings.MQTT_BROKER_PORT)
            self.client.connect_async(
                host=settings.MQTT_BROKER_HOST,
                port=settings.MQTT_BROKER_PORT,
                keepalive=60,
            )
            self.client.loop_start()
        except Exception as exc:
            logger.warning("MQTT background loop start failed: %s (broker may be unreachable)", exc)

    def stop(self) -> None:
        """Stop network loop and disconnect."""
        try:
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("MQTT consumer stopped.")
        except Exception as exc:
            logger.warning("Error stopping MQTT consumer: %s", exc)


# Global consumer instance (can be started optionally via app lifecycle or worker)
mqtt_consumer = MQTTTelemetryConsumer()
