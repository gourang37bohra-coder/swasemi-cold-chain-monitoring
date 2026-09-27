"""Unit tests for Model 8: Cold-Chain Device Simulator."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

# Ensure simulator package is importable
repo_root = Path(__file__).resolve().parent.parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from simulator.config import SimulatorSettings, TrackerConfig
from simulator.device import SimulatedTracker
from simulator.engine import SimulatorEngine
from simulator.movement import RouteModel
from simulator.sensors import SensorSimulator
from simulator.shipment_gate import ActiveShipmentInfo, ShipmentGateClient


def test_payload_generation_schema():
    """1. Test that active tracker generates schema-conformant telemetry payload."""
    cfg = TrackerConfig(
        tracker_id="73908884-4df0-4afb-965f-2815e6d11adc",
        name="Apex Cold-Box 101",
        mqtt_topic="coldchain/trackers/73908884-4df0-4afb-965f-2815e6d11adc/telemetry",
        initial_lat=19.1670,
        initial_lon=72.9320,
        route_name="mumbai_pune",
        default_temp_min=2.0,
        default_temp_max=8.0,
    )
    tracker = SimulatedTracker(cfg)
    tracker.update_shipment(
        ActiveShipmentInfo(
            shipment_id="576075c6-15c4-4b45-a4d0-63a6d9f9b7d5",
            tracker_id=cfg.tracker_id,
            status="ACTIVE",
            min_temperature=2.0,
            max_temperature=8.0,
        )
    )

    payload = tracker.tick(temp_mode="normal")
    assert payload is not None
    assert payload["tracker_id"] == cfg.tracker_id
    assert "timestamp" in payload
    assert isinstance(payload["temperature"], float)
    assert isinstance(payload["latitude"], float)
    assert isinstance(payload["longitude"], float)
    assert isinstance(payload["humidity"], float)
    assert isinstance(payload["battery"], float)
    assert isinstance(payload["door_status"], bool)


def test_gps_movement_advances_continuously():
    """2. Test that GPS coordinates advance gradually along route without teleporting."""
    route = RouteModel("mumbai_pune", step_distance_deg=0.002)
    start_lat, start_lon = route.get_position()

    lat1, lon1 = route.advance()
    assert (lat1 != start_lat) or (lon1 != start_lon)

    # Verify movement step size is bounded (no large jumps/teleporting)
    dist = ((lat1 - start_lat) ** 2 + (lon1 - start_lon) ** 2) ** 0.5
    assert dist <= 0.003


def test_temperature_normal_vs_breach():
    """3. Test temperature generation within bounds for normal mode and excursion in breach mode."""
    sensors = SensorSimulator(temp_min=2.0, temp_max=8.0)

    # Normal mode must stay within safe window
    for _ in range(10):
        temp, _, _, _ = sensors.generate(mode="normal")
        assert 2.0 <= temp <= 8.0

    # Breach mode must simulate excursion exceeding maximum threshold
    for _ in range(20):
        temp, _, _, _ = sensors.generate(mode="breach")
    assert temp > 8.0


def test_battery_drain_behavior():
    """4. Test that battery decreases gradually and does not jump or drain instantly."""
    sensors = SensorSimulator(initial_battery=100.0, battery_drain_rate=0.05)
    _, _, b1, _ = sensors.generate()
    _, _, b2, _ = sensors.generate()
    assert b1 < 100.0
    assert b2 < b1
    assert b2 >= 99.8  # only minor drain per tick


def test_door_status_generation():
    """5. Test door status is boolean and primarily closed."""
    sensors = SensorSimulator()
    doors = [sensors.generate()[3] for _ in range(30)]
    assert all(isinstance(d, bool) for d in doors)
    assert doors.count(False) > doors.count(True)  # mostly closed


def test_shipment_inactive_blocks_telemetry():
    """6. P0 Gate: Inactive tracker (no active shipment) MUST NOT generate telemetry."""
    cfg = TrackerConfig(
        tracker_id="52a2dc8c-c613-4546-836d-6c64e49a15aa",
        name="Apex Cold-Box 102",
        mqtt_topic="coldchain/trackers/52a2dc8c-c613-4546-836d-6c64e49a15aa/telemetry",
        initial_lat=19.0760,
        initial_lon=72.8777,
        route_name="city_depot",
    )
    tracker = SimulatedTracker(cfg)
    assert tracker.is_active is False
    payload = tracker.tick()
    assert payload is None


def test_shipment_active_permits_telemetry():
    """7. Tracker with ACTIVE shipment begins generating telemetry."""
    cfg = TrackerConfig(
        tracker_id="b140093e-b69b-4ab5-92e3-1a97e6cd6a62",
        name="Medical_UnitA",
        mqtt_topic="coldchain/trackers/b140093e-b69b-4ab5-92e3-1a97e6cd6a62/telemetry",
        initial_lat=19.0657,
        initial_lon=72.8687,
        route_name="coastal_north",
    )
    tracker = SimulatedTracker(cfg)
    tracker.update_shipment(
        ActiveShipmentInfo(
            shipment_id="9b4f58a8-40c0-4545-a5cb-d99fc6af8b72",
            tracker_id=cfg.tracker_id,
            status="ACTIVE",
            min_temperature=1.0,
            max_temperature=3.0,
        )
    )
    assert tracker.is_active is True
    payload = tracker.tick()
    assert payload is not None
    assert payload["tracker_id"] == cfg.tracker_id


def test_multiple_trackers_operate_independently():
    """8. Test that multiple trackers move independently along different routes."""
    cfg_a = TrackerConfig("id-a", "Tracker A", "topic/a", 19.1670, 72.9320, "mumbai_pune")
    cfg_b = TrackerConfig("id-b", "Tracker B", "topic/b", 19.0657, 72.8687, "coastal_north")
    cfg_c = TrackerConfig("id-c", "Tracker C", "topic/c", 19.2967, 73.0631, "inland_nashik")

    t_a = SimulatedTracker(cfg_a)
    t_b = SimulatedTracker(cfg_b)
    t_c = SimulatedTracker(cfg_c)

    for t in (t_a, t_b, t_c):
        t.update_shipment(ActiveShipmentInfo("ship-id", t.tracker_id, "ACTIVE", 2.0, 8.0))

    p_a1 = t_a.tick()
    p_b1 = t_b.tick()
    p_c1 = t_c.tick()

    # Trackers must have distinct coordinates matching their distinct routes
    assert (p_a1["latitude"], p_a1["longitude"]) != (p_b1["latitude"], p_b1["longitude"])
    assert (p_b1["latitude"], p_b1["longitude"]) != (p_c1["latitude"], p_c1["longitude"])


def test_simulator_engine_publish_cycle():
    """9. Test SimulatorEngine publish_cycle publishes only for active trackers using mocked MQTT client."""
    settings = SimulatorSettings()
    engine = SimulatorEngine(settings)
    engine.mqtt_client = MagicMock()

    # Mark Tracker 1 and Tracker 2 as ACTIVE, leave Tracker 4 as INACTIVE
    t1_id = settings.trackers[0].tracker_id
    t2_id = settings.trackers[1].tracker_id
    engine.trackers[t1_id].update_shipment(ActiveShipmentInfo("s1", t1_id, "ACTIVE", 2.0, 8.0))
    engine.trackers[t2_id].update_shipment(ActiveShipmentInfo("s2", t2_id, "ACTIVE", 1.0, 3.0))

    with patch.object(engine, "refresh_shipments"):  # avoid real network call in unit test
        count = engine.publish_cycle()

    assert count >= 2
    assert engine.mqtt_client.publish.call_count == count
