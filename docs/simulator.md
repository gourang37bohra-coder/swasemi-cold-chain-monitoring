# Cold-Chain Device Simulator (Model 8)

## 1. Overview & Purpose

The **SWASEMI Cold-Chain Device Simulator** simulates the hardware/device side of the cold-chain IoT tracking system. It generates realistic, deterministic GPS trajectories, sensor readings (temperature, humidity, battery level, and door status), and publishes MQTT telemetry messages over the public MQTT broker (`broker.emqx.io`).

The simulator operates as an external system and enforces the **P0 Shipment Lifecycle Gate**: telemetry is generated and transmitted **only** for trackers that currently have an `ACTIVE` shipment registered in the backend.

```
┌─────────────────────────────────────────────────────────────┐
│                    DEVICE SIMULATOR                         │
│                                                             │
│  [Tracker A: Apex Cold-Box 101]   Route: Mumbai ➔ Pune      │
│  [Tracker B: Medical_UnitA]       Route: Coastal North      │
│  [Tracker C: Medical_UnitB]       Route: Inland Nashik      │
│  [Tracker D: Apex Cold-Box 102]   (INACTIVE / Gated)        │
└──────────────┬───────────────────────────────▲──────────────┘
               │                               │
    Publish Telemetry (MQTT)         Poll Active Shipments
               ▼                               ▼
       [broker.emqx.io]            [FastAPI: GET /shipments]
               │                               │
               ▼                               │
      FastAPI MQTT Consumer                    │
               │                               │
               ├───────────────────────────────┤
               ▼                               ▼
       [PostgreSQL DB]                 [Redis Pub/Sub]
               │                               │
               │                               ▼
               │                        WebSocket Bridge
               │                               │
               └───────────────┬───────────────┘
                               ▼
                       [React Dashboard]
                    (Real-Time Moving Fleet)
```

---

## 2. Architecture & Components

The simulator is located in `simulator/` and is fully decoupled from `backend/app/`:

- `simulator/config.py`: Configuration settings loaded from environment variables and default tracker profiles.
- `simulator/movement.py`: Deterministic waypoint-based movement model that advances GPS coordinates along real logistics corridors in Maharashtra without jumping or teleporting.
- `simulator/sensors.py`: Realistic sensor generator simulating temperature within safe bounds (or breach excursion), gradual humidity fluctuations, battery drain, and cargo door opening/closing events.
- `simulator/shipment_gate.py`: REST client that connects to the backend API (`/auth/login` and `/shipments`), keeping active shipments indexed by `tracker_id`.
- `simulator/device.py`: `SimulatedTracker` class encapsulating device state, coordinates, sensors, and shipment lifecycle gating.
- `simulator/engine.py`: `SimulatorEngine` managing the MQTT connection pool, periodic tick cycles, logging, and graceful shutdown.
- `simulator/main.py`: Command-line interface with argument parsing and signal handling.

---

## 3. Installation & Dependencies

The simulator uses standard Python libraries and `paho-mqtt` (already included in the project virtual environment):

```bash
# Optional standalone requirements
pip install paho-mqtt
```

---

## 4. Configuration & Environment Variables

All settings are configurable via environment variables or CLI flags:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `MQTT_BROKER_HOST` | `broker.emqx.io` | MQTT Broker hostname |
| `MQTT_BROKER_PORT` | `1883` | MQTT Broker port |
| `MQTT_USERNAME` | `None` | Optional MQTT username |
| `MQTT_PASSWORD` | `None` | Optional MQTT password |
| `MQTT_TLS` | `false` | Enable TLS encryption |
| `BACKEND_API_URL` | `http://127.0.0.1:8000` | FastAPI backend base URL |
| `API_USERNAME` | `operator@apexpharma.com` | Tenant operator email for shipment queries |
| `API_PASSWORD` | `Password@123` | Tenant operator password |
| `SIMULATOR_INTERVAL_SECONDS` | `5.0` | Telemetry publishing interval (seconds) |
| `SHIPMENT_REFRESH_INTERVAL_SECONDS` | `10.0` | Interval to re-check shipment statuses |
| `SIMULATOR_TEMPERATURE_MODE` | `normal` | Simulation mode: `normal` or `breach` |

---

## 5. Pre-Configured Trackers

The simulator is pre-configured with four real database trackers belonging to `Apex Pharma Global`:

1. **Tracker 1: Apex Cold-Box 101**
   - **Tracker ID:** `73908884-4df0-4afb-965f-2815e6d11adc`
   - **Topic:** `coldchain/trackers/73908884-4df0-4afb-965f-2815e6d11adc/telemetry`
   - **Route:** `mumbai_pune` (Thane ➔ Belapur ➔ Panvel ➔ Lonavala ➔ Pune)
   - **Target Range:** 2.0°C – 8.0°C

2. **Tracker 2: Medical_UnitA**
   - **Tracker ID:** `b140093e-b69b-4ab5-92e3-1a97e6cd6a62`
   - **Topic:** `coldchain/trackers/b140093e-b69b-4ab5-92e3-1a97e6cd6a62/telemetry`
   - **Route:** `coastal_north` (BKC ➔ Andheri ➔ Borivali ➔ Vasai ➔ Palghar)
   - **Target Range:** 1.0°C – 3.0°C

3. **Tracker 3: Medical_UnitB**
   - **Tracker ID:** `05d3d094-58c7-41ff-b57e-a772948539d6`
   - **Topic:** `coldchain/trackers/05d3d094-58c7-41ff-b57e-a772948539d6/telemetry`
   - **Route:** `inland_nashik` (Bhiwandi ➔ Kalyan ➔ Asangaon ➔ Kasara ➔ Nashik)
   - **Target Range:** 4.0°C – 8.0°C

4. **Tracker 4: Apex Cold-Box 102** (Lifecycle Gating Test)
   - **Tracker ID:** `52a2dc8c-c613-4546-836d-6c64e49a15aa`
   - **Topic:** `coldchain/trackers/52a2dc8c-c613-4546-836d-6c64e49a15aa/telemetry`
   - **Status:** Inactive (`NOT_STARTED` / No Active Shipment)
   - **Behavior:** Gated; zero telemetry published until a shipment is started.

---

## 6. How to Run the Simulator

From the repository root:

```bash
# Standard normal run (5-second intervals, safe temperatures)
python -m simulator.main

# Custom interval (e.g., 3-second cycle for faster demo)
python -m simulator.main --interval 3.0

# Temperature breach mode (simulates temperature excursions above threshold)
python -m simulator.main --mode breach

# Custom broker or API URL
python -m simulator.main --broker broker.emqx.io --api-url http://127.0.0.1:8000
```

### Stopping the Simulator
Press `Ctrl+C`. The simulator catches `SIGINT`, cleanly disconnects from `broker.emqx.io`, and terminates without hanging processes.

---

## 7. Shipment Lifecycle Gate Enforcement

The simulator enforces the following gate logic on every cycle:

- **Before Shipment Starts (`NOT_STARTED`):**
  - Tracker exists in fleet.
  - Simulator queries backend and detects status is not `ACTIVE`.
  - Simulator logs `[SIM-GATE] Skipped` and **does not publish** MQTT telemetry.
- **After Start Shipment (`POST /shipments/{id}/start`):**
  - Simulator detects state transition to `ACTIVE` on the next refresh cycle.
  - Simulator begins publishing telemetry messages at the configured interval.
- **After Complete Shipment (`POST /shipments/{id}/complete`):**
  - Simulator detects state transition to `COMPLETED`.
  - Simulator **immediately halts publishing** for that tracker. Remaining active trackers continue uninterrupted.

---

## 8. Telemetry Message Format

Payloads published to `coldchain/trackers/{tracker_id}/telemetry` follow the schema:

```json
{
  "tracker_id": "73908884-4df0-4afb-965f-2815e6d11adc",
  "timestamp": "2026-09-27T11:23:45.123456Z",
  "temperature": 5.14,
  "latitude": 19.16602,
  "longitude": 72.93086,
  "humidity": 54.2,
  "battery": 97.4,
  "door_status": false
}
```

---

## 9. Demonstrating Live Fleet Movement on the Dashboard

1. **Start backend services** (PostgreSQL, Redis, FastAPI).
2. **Start frontend** (`npm run dev` at `http://localhost:5173`).
3. **Log in** as `operator@apexpharma.com` (`Password@123`).
4. **Start the simulator:**
   ```bash
   python -m simulator.main --interval 4.0
   ```
5. **Observe:**
   - Simulator console prints published telemetry with changing GPS coordinates.
   - On the web dashboard, the **Live Asset Fleet Map** displays all 3 active trackers moving in real time.
   - Click any marker to view live temperature, battery percentage, door status, and updated GPS coordinates.
   - On the **Shipment Detail** view, observe the live temperature chart and expanding GPS breadcrumb trail.
6. **Test the Shipment Gate:**
   - In the frontend UI or via API, complete one shipment (e.g. `Medical_UnitB`).
   - Observe in the simulator logs that `Medical_UnitB` immediately transitions to `[SIM-GATE] INACTIVE | Skipped`, while the other two trackers continue moving and publishing.

---

## 10. Troubleshooting

| Issue | Cause | Solution |
| :--- | :--- | :--- |
| `Failed to connect to MQTT broker` | Internet or DNS issue connecting to `broker.emqx.io:1883` | Verify internet connection or test `Test-NetConnection -ComputerName broker.emqx.io -Port 1883`. |
| `Could not refresh shipments from backend` | Backend is not running or credentials invalid | Ensure backend is running on `http://127.0.0.1:8000` and credentials match `.env`. |
| `Tracker skipped with [SIM-GATE]` | Tracker has no `ACTIVE` shipment | Start a shipment assigned to that tracker via the frontend UI or `POST /shipments/{id}/start`. |
