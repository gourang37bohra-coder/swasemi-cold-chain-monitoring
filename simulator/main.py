"""CLI entry point for running the SWASEMI Cold-Chain Device Simulator."""

import argparse
import logging
import signal
import sys

from simulator.config import settings
from simulator.engine import SimulatorEngine


def configure_logging(level: int = logging.INFO) -> None:
    """Set up clean console logging format for simulator outputs."""
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    
    root_logger = logging.getLogger("coldchain.simulator")
    root_logger.setLevel(level)
    root_logger.handlers = [handler]


def main() -> None:
    """Parse CLI options and run the simulation engine."""
    parser = argparse.ArgumentParser(
        description="SWASEMI Cold-Chain IoT Device Simulator (MQTT Publisher)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=settings.publish_interval_seconds,
        help="Publishing interval in seconds (default: 5.0)",
    )
    parser.add_argument(
        "--mode",
        choices=["normal", "breach"],
        default=settings.temperature_mode,
        help="Temperature simulation mode: 'normal' (safe range) or 'breach' (high temp alarm)",
    )
    parser.add_argument(
        "--broker",
        default=settings.mqtt_broker_host,
        help="MQTT broker hostname (default: broker.emqx.io)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=settings.mqtt_broker_port,
        help="MQTT broker port (default: 1883)",
    )
    parser.add_argument(
        "--api-url",
        default=settings.backend_api_url,
        help="Backend REST API URL for active shipment queries (default: http://127.0.0.1:8000)",
    )

    args = parser.parse_args()

    # Apply CLI overrides
    settings.publish_interval_seconds = args.interval
    settings.temperature_mode = args.mode
    settings.mqtt_broker_host = args.broker
    settings.mqtt_broker_port = args.port
    settings.backend_api_url = args.api_url

    configure_logging()

    engine = SimulatorEngine(settings)

    # Attach signal handlers for graceful shutdown
    def handle_signal(sig, frame):
        print("\nStopping simulator...")
        engine.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    engine.start()


if __name__ == "__main__":
    main()
