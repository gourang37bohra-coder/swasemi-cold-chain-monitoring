"""Sensor simulation models for temperature, humidity, battery, and door status."""

import random
from typing import Tuple


class SensorSimulator:
    """Simulates realistic telemetry readings for cold-chain sensors."""

    def __init__(
        self,
        temp_min: float = 2.0,
        temp_max: float = 8.0,
        initial_battery: float = 100.0,
        battery_drain_rate: float = 0.02,
    ) -> None:
        self.temp_min = temp_min
        self.temp_max = temp_max
        self.current_temp = (temp_min + temp_max) / 2.0
        self.current_humidity = 55.0
        self.battery = initial_battery
        self.battery_drain_rate = battery_drain_rate
        self.door_status = False
        self._cycle_count = 0

    def set_temperature_bounds(self, temp_min: float, temp_max: float) -> None:
        """Update active temperature bounds from shipment configuration."""
        self.temp_min = temp_min
        self.temp_max = temp_max

    def generate(self, mode: str = "normal") -> Tuple[float, float, float, bool]:
        """Generate one cycle of sensor readings (temperature, humidity, battery, door_status)."""
        self._cycle_count += 1

        # 1. Temperature Simulation
        if mode == "breach":
            # Simulate a temperature excursion exceeding upper threshold
            target_temp = self.temp_max + 2.5
            drift = (target_temp - self.current_temp) * 0.2 + random.uniform(-0.1, 0.2)
            self.current_temp = round(self.current_temp + drift, 2)
        else:
            # Normal operation: maintain temperature within safe target window
            target_midpoint = (self.temp_min + self.temp_max) / 2.0
            restoring_force = (target_midpoint - self.current_temp) * 0.1
            noise = random.uniform(-0.2, 0.2)
            new_temp = self.current_temp + restoring_force + noise
            # Clamp strictly within configured safe bounds for normal mode
            margin = max(0.2, (self.temp_max - self.temp_min) * 0.1)
            self.current_temp = round(
                max(self.temp_min + margin, min(self.temp_max - margin, new_temp)),
                2,
            )

        # 2. Humidity Simulation (gradual random walk bounded between 40% and 75%)
        humidity_drift = random.uniform(-0.4, 0.4)
        self.current_humidity = round(
            max(40.0, min(75.0, self.current_humidity + humidity_drift)),
            1,
        )

        # 3. Battery Simulation (gradual linear drain clamped at 0.0%)
        self.battery = round(max(0.0, self.battery - self.battery_drain_rate), 2)

        # 4. Door Status Simulation (mostly closed, brief occasional access every 25 cycles)
        if self._cycle_count % 25 in (0, 1):
            self.door_status = True
        else:
            self.door_status = False

        return self.current_temp, self.current_humidity, self.battery, self.door_status
