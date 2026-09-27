"""Simulator engine managing MQTT publishing loop, tracker fleet, and lifecycle gates."""

import json
import logging
import time
from typing import Dict, List, Optional
import uuid

import paho.mqtt.client as mqtt

from simulator.config import SimulatorSettings, TrackerConfig
from simulator.device import SimulatedTracker
from simulator.shipment_gate import ShipmentGateClient

logger = logging.getLogger("coldchain.simulator")


class SimulatorEngine:
    """Orchestrates the cold-chain tracker device simulation fleet."""

    def __init__(self, settings: SimulatorSettings) -> None:
        self.settings = settings
        self.gate_client = ShipmentGateClient(
            base_url=settings.backend_api_url,
            username=settings.api_username,
            password=settings.api_password,
        )

        # Initialize fleet of simulated trackers
        self.trackers: Dict[str, SimulatedTracker] = {}
        for cfg in settings.trackers:
            self.trackers[str(cfg.tracker_id)] = SimulatedTracker(cfg)

        # MQTT Client initialization
        client_id = settings.mqtt_client_id or f"coldchain-sim-{uuid.uuid4().hex[:8]}"
        self.mqtt_client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
        )
        if settings.mqtt_username:
            self.mqtt_client.username_pw_set(
                username=settings.mqtt_username,
                password=settings.mqtt_password,
            )
        if settings.mqtt_tls:
            self.mqtt_client.tls_set()

        self.mqtt_client.on_connect = self._on_connect
        self.mqtt_client.on_disconnect = self._on_disconnect
        self._is_connected = False
        self._running = False
        self._last_shipment_refresh = 0.0

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self._is_connected = True
            logger.info("Connected to MQTT broker at %s:%s", self.settings.mqtt_broker_host, self.settings.mqtt_broker_port)
        else:
            logger.error("Failed to connect to MQTT broker, return code: %s", rc)

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties=None):
        self._is_connected = False
        logger.warning("Disconnected from MQTT broker (code: %s)", reason_code)

    def refresh_shipments(self) -> None:
        """Poll backend API and update active shipment bindings for all trackers."""
        try:
            active_map = self.gate_client.refresh_active_shipments()
            for t_id, tracker in self.trackers.items():
                shipment_info = active_map.get(t_id)
                tracker.update_shipment(shipment_info)
        except Exception as exc:
            logger.warning("Could not refresh shipments from backend: %s", exc)

    def publish_cycle(self) -> int:
        """Execute one simulation cycle across all trackers.
        
        Returns the count of successfully published telemetry messages.
        """
        # Periodically refresh shipment gate status
        now = time.time()
        if now - self._last_shipment_refresh >= self.settings.shipment_refresh_interval_seconds:
            self.refresh_shipments()
            self._last_shipment_refresh = now

        published_count = 0
        for t_id, tracker in self.trackers.items():
            payload = tracker.tick(temp_mode=self.settings.temperature_mode)

            if payload is None:
                logger.info(
                    "[SIM-GATE] Tracker: %-18s (%s) | Status: INACTIVE (No active shipment) | Skipped",
                    tracker.name,
                    t_id[:8],
                )
                continue

            payload_json = json.dumps(payload)
            topic = tracker.mqtt_topic

            try:
                info = self.mqtt_client.publish(topic, payload_json, qos=0)
                published_count += 1
                logger.info(
                    "[SIM-PUBLISH] Tracker: %-18s | Temp: %5.1f°C | GPS: %8.4f, %8.4f | Bat: %5.1f%% | Door: %-5s | Topic: %s",
                    tracker.name,
                    payload["temperature"],
                    payload["latitude"],
                    payload["longitude"],
                    payload["battery"],
                    "OPEN" if payload["door_status"] else "CLOSED",
                    topic,
                )
            except Exception as exc:
                logger.error("Error publishing telemetry for %s: %s", tracker.name, exc)

        return published_count

    def start(self) -> None:
        """Connect to MQTT broker and run the simulation loop until stopped."""
        logger.info(
            "Starting Cold-Chain Device Simulator (Broker: %s:%s, Interval: %.1fs, TempMode: %s)",
            self.settings.mqtt_broker_host,
            self.settings.mqtt_broker_port,
            self.settings.publish_interval_seconds,
            self.settings.temperature_mode,
        )

        try:
            self.mqtt_client.connect(
                host=self.settings.mqtt_broker_host,
                port=self.settings.mqtt_broker_port,
                keepalive=60,
            )
            self.mqtt_client.loop_start()
        except Exception as exc:
            logger.error("Failed to connect to MQTT broker: %s", exc)
            return

        # Initial shipment lookup
        self.refresh_shipments()
        self._last_shipment_refresh = time.time()
        self._running = True

        logger.info("Simulator running with %d configured trackers. Press Ctrl+C to stop.", len(self.trackers))

        try:
            while self._running:
                self.publish_cycle()
                time.sleep(self.settings.publish_interval_seconds)
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received, stopping simulator...")
        finally:
            self.stop()

    def stop(self) -> None:
        """Gracefully disconnect MQTT client and terminate loops."""
        self._running = False
        try:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            logger.info("Simulator stopped cleanly.")
        except Exception as exc:
            logger.warning("Error stopping MQTT client: %s", exc)
