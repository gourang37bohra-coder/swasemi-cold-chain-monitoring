"""Device model representing an individual cold-chain IoT tracker."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from simulator.config import TrackerConfig
from simulator.movement import RouteModel
from simulator.sensors import SensorSimulator
from simulator.shipment_gate import ActiveShipmentInfo


class SimulatedTracker:
    """Manages the lifecycle, GPS movements, sensor dynamics, and telemetry generation of a tracker."""

    def __init__(self, config: TrackerConfig) -> None:
        self.tracker_id = str(config.tracker_id)
        self.name = config.name
        self.mqtt_topic = config.mqtt_topic
        self.movement = RouteModel(config.route_name)
        self.sensors = SensorSimulator(
            temp_min=config.default_temp_min,
            temp_max=config.default_temp_max,
        )
        self.active_shipment: Optional[ActiveShipmentInfo] = None

    def update_shipment(self, shipment_info: Optional[ActiveShipmentInfo]) -> None:
        """Update active shipment status and temperature boundaries."""
        self.active_shipment = shipment_info
        if shipment_info:
            self.sensors.set_temperature_bounds(
                temp_min=shipment_info.min_temperature,
                temp_max=shipment_info.max_temperature,
            )

    @property
    def is_active(self) -> bool:
        """Return True if tracker currently has an active shipment."""
        return self.active_shipment is not None

    def tick(self, temp_mode: str = "normal") -> Optional[Dict[str, Any]]:
        """Advance tracker position and sensors.
        
        Returns schema-compliant telemetry payload if an active shipment exists,
        or None if no shipment is active (P0 shipment gate enforcement).
        """
        # P0 GATE: Telemetry is generated ONLY when shipment is ACTIVE
        if not self.is_active:
            return None

        # 1. Advance GPS position along route
        lat, lon = self.movement.advance()

        # 2. Generate sensor readings
        temp, humidity, battery, door_status = self.sensors.generate(mode=temp_mode)

        # 3. Format telemetry payload matching backend TelemetryPayload schema
        payload = {
            "tracker_id": self.tracker_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "temperature": temp,
            "latitude": lat,
            "longitude": lon,
            "humidity": humidity,
            "battery": battery,
            "door_status": door_status,
        }

        return payload
