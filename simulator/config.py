"""Configuration module for the SWASEMI Cold-Chain Device Simulator."""

import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TrackerConfig:
    """Configuration profile for a simulated IoT tracker device."""
    tracker_id: str
    name: str
    mqtt_topic: str
    initial_lat: float
    initial_lon: float
    route_name: str
    default_temp_min: float = 2.0
    default_temp_max: float = 8.0


@dataclass
class SimulatorSettings:
    """Global configuration settings for the device simulator."""
    # MQTT Broker Configuration
    mqtt_broker_host: str = field(
        default_factory=lambda: os.getenv("MQTT_BROKER_HOST", "broker.emqx.io")
    )
    mqtt_broker_port: int = field(
        default_factory=lambda: int(os.getenv("MQTT_BROKER_PORT", "1883"))
    )
    mqtt_username: Optional[str] = field(
        default_factory=lambda: os.getenv("MQTT_USERNAME", None)
    )
    mqtt_password: Optional[str] = field(
        default_factory=lambda: os.getenv("MQTT_PASSWORD", None)
    )
    mqtt_tls: bool = field(
        default_factory=lambda: os.getenv("MQTT_TLS", "false").lower() in ("true", "1", "yes")
    )
    mqtt_client_id: Optional[str] = field(
        default_factory=lambda: os.getenv("MQTT_CLIENT_ID", None)
    )

    # Backend API Configuration (for active shipment queries)
    backend_api_url: str = field(
        default_factory=lambda: os.getenv("BACKEND_API_URL", "http://127.0.0.1:8000")
    )
    api_username: str = field(
        default_factory=lambda: os.getenv("API_USERNAME", "operator@apexpharma.com")
    )
    api_password: str = field(
        default_factory=lambda: os.getenv("API_PASSWORD", "Password@123")
    )

    # Simulator Behavior
    publish_interval_seconds: float = field(
        default_factory=lambda: float(os.getenv("SIMULATOR_INTERVAL_SECONDS", "5.0"))
    )
    shipment_refresh_interval_seconds: float = field(
        default_factory=lambda: float(os.getenv("SHIPMENT_REFRESH_INTERVAL_SECONDS", "10.0"))
    )
    temperature_mode: str = field(
        default_factory=lambda: os.getenv("SIMULATOR_TEMPERATURE_MODE", "normal").lower()
    )

    # Pre-configured Real Database Trackers with Distinct Regional Logistics Corridors
    trackers: List[TrackerConfig] = field(
        default_factory=lambda: [
            # 1. Maharashtra Corridor (Mumbai to Pune)
            TrackerConfig(
                tracker_id=os.getenv("TRACKER_1_ID", "73908884-4df0-4afb-965f-2815e6d11adc"),
                name=os.getenv("TRACKER_1_NAME", "Apex Cold-Box 101"),
                mqtt_topic=os.getenv("TRACKER_1_TOPIC", "coldchain/trackers/73908884-4df0-4afb-965f-2815e6d11adc/telemetry"),
                initial_lat=19.0760,
                initial_lon=72.8777,
                route_name="mumbai_pune",
                default_temp_min=2.0,
                default_temp_max=8.0,
            ),
            # 2. Gujarat Corridor (Ahmedabad to Surat)
            TrackerConfig(
                tracker_id=os.getenv("TRACKER_2_ID", "b140093e-b69b-4ab5-92e3-1a97e6cd6a62"),
                name=os.getenv("TRACKER_2_NAME", "Medical_UnitA"),
                mqtt_topic=os.getenv("TRACKER_2_TOPIC", "coldchain/trackers/b140093e-b69b-4ab5-92e3-1a97e6cd6a62/telemetry"),
                initial_lat=23.0225,
                initial_lon=72.5714,
                route_name="gujarat_corridor",
                default_temp_min=1.0,
                default_temp_max=3.0,
            ),
            # 3. Madhya Pradesh Corridor (Indore to Bhopal)
            TrackerConfig(
                tracker_id=os.getenv("TRACKER_3_ID", "05d3d094-58c7-41ff-b57e-a772948539d6"),
                name=os.getenv("TRACKER_3_NAME", "Medical_UnitB"),
                mqtt_topic=os.getenv("TRACKER_3_TOPIC", "coldchain/trackers/05d3d094-58c7-41ff-b57e-a772948539d6/telemetry"),
                initial_lat=22.7196,
                initial_lon=75.8577,
                route_name="mp_corridor",
                default_temp_min=4.0,
                default_temp_max=8.0,
            ),
            # 4. Rajasthan Corridor (Jaipur to Ajmer - Inactive Tracker for gating demo)
            TrackerConfig(
                tracker_id=os.getenv("TRACKER_4_ID", "52a2dc8c-c613-4546-836d-6c64e49a15aa"),
                name=os.getenv("TRACKER_4_NAME", "Apex Cold-Box 102"),
                mqtt_topic=os.getenv("TRACKER_4_TOPIC", "coldchain/trackers/52a2dc8c-c613-4546-836d-6c64e49a15aa/telemetry"),
                initial_lat=26.9124,
                initial_lon=75.7873,
                route_name="rajasthan_corridor",
                default_temp_min=2.0,
                default_temp_max=8.0,
            ),
        ]
    )


settings = SimulatorSettings()
