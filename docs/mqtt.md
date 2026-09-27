# MQTT Telemetry Ingestion Architecture (Model 5)

This document describes the MQTT telemetry ingestion pipeline, active-shipment gating, payload validation, database persistence, and security controls implemented in Model 5 of the SWASEMI Cold-Chain Monitoring Platform.

---

## 1. Overview & Architecture

```
[ IoT Tracker / Device ]
       │
       ▼ MQTT Publish (e.g. coldchain/trackers/{tracker_id}/telemetry)
[ MQTT Broker (e.g. EMQX / Mosquitto) ]
       │
       ▼ Wildcard Subscription (coldchain/trackers/+/telemetry)
[ MQTTTelemetryConsumer (app/mqtt/client.py) ]
       │
       ▼ Safe JSON & Schema Validation (app/schemas/telemetry.py)
[ Ingestion Service (app/services/telemetry_ingestion.py) ]
       │
       ├── 1. Resolve Tracker from PostgreSQL
       ├── 2. Derive organization_id from Tracker (spoof-proof)
       ├── 3. ACTIVE-SHIPMENT GATE: Is shipment currently ACTIVE?
       │      ├── NO  ──▶ Discard telemetry (do NOT persist)
       │      └── YES ──▶ Check duplicate (tracker_id, timestamp)
       ▼
[ PostgreSQL: Persist Telemetry & Update Tracker.last_seen ]
```

---

## 2. Broker Configuration

The MQTT client is implemented using `paho-mqtt` (v2.x) and is configured via environment variables:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `MQTT_BROKER_HOST` | `broker.emqx.io` | Hostname or IP of the MQTT broker |
| `MQTT_BROKER_PORT` | `1883` | Port for plain MQTT (or `8883` for TLS) |
| `MQTT_USERNAME` | `null` | Optional username for broker authentication |
| `MQTT_PASSWORD` | `null` | Optional password for broker authentication |
| `MQTT_TLS` | `false` | Enable TLS encryption |
| `MQTT_TOPIC_PREFIX` | `coldchain/trackers` | Topic prefix for telemetry subscriptions |
| `MQTT_CLIENT_ID` | `null` | Optional unique client ID (auto-generated if omitted) |

> [!SECURITY]
> Connection credentials, usernames, and passwords are never logged or exposed in API responses.

---

## 3. Topic Structure

Trackers publish sensor readings to their designated topic:
```
coldchain/trackers/{tracker_id}/telemetry
```
- `{tracker_id}`: Standard UUID string of the tracker.
- The consumer subscribes to the wildcard pattern: `{MQTT_TOPIC_PREFIX}/+/telemetry`.

---

## 4. Telemetry Payload Format

Incoming messages must be valid JSON matching the `TelemetryPayload` schema:

```json
{
  "tracker_id": "4b684cb3-0b0f-488f-9a4f-69ff32a514d7",
  "timestamp": "2026-09-26T18:45:00Z",
  "temperature": 4.25,
  "latitude": 37.7749,
  "longitude": -122.4194,
  "humidity": 48.0,
  "battery": 95.0,
  "door_status": false
}
```

### Validation Rules
- `tracker_id`: Required UUID.
- `timestamp`: Required ISO-8601 UTC timestamp.
- `temperature`: Required float (°C).
- `latitude`: Required float, bounded `[-90.0, 90.0]`.
- `longitude`: Required float, bounded `[-180.0, 180.0]`.
- `humidity`: Optional float, bounded `[0.0, 100.0]` (defaults to `50.0`).
- `battery`: Optional float, bounded `[0.0, 100.0]` (defaults to `100.0`).
- `door_status`: Optional boolean (defaults to `false`).

---

## 5. Active-Shipment Gating (Critical Business Rule)

Telemetry is **STRICTLY PERSISTED ONLY WHEN THE TRACKER HAS AN ACTIVE SHIPMENT**.

| Tracker State | Shipment State | Ingestion Action | Database Effect |
| :--- | :--- | :--- | :--- |
| Exists in DB | `ACTIVE` | **Accepted** | Telemetry persisted; `tracker.last_seen` updated |
| Exists in DB | `NOT_STARTED` | **Rejected** (`REJECTED_NO_ACTIVE_SHIPMENT`) | No telemetry persisted; `last_seen` unchanged |
| Exists in DB | `COMPLETED` | **Rejected** (`REJECTED_NO_ACTIVE_SHIPMENT`) | No telemetry persisted; `last_seen` unchanged |
| Exists in DB | No shipment attached | **Rejected** (`REJECTED_NO_ACTIVE_SHIPMENT`) | No telemetry persisted; `last_seen` unchanged |
| Does not exist in DB | Any | **Rejected** (`REJECTED_UNKNOWN_TRACKER`) | No telemetry persisted |

---

## 6. Tenant Security & Anti-Spoofing

- **Organization Derivation**: The `organization_id` for each telemetry record is **derived exclusively from the PostgreSQL `trackers` table**.
- **Anti-Spoofing**: If an incoming payload contains an `organization_id` field (malicious attempt to inject telemetry into another tenant), the field is ignored. Telemetry is saved with the tracker's real `organization_id`.
- **Composite Foreign Key**: Telemetry rows enforce `(tracker_id, organization_id)` and `(shipment_id, organization_id)` foreign keys, guaranteeing cross-tenant relationships cannot be created in PostgreSQL.

---

## 7. Idempotency & Duplicate Handling

- Duplicate messages (e.g. caused by MQTT QoS 1 re-deliveries) sharing the same `(tracker_id, timestamp)` are detected at the application layer via indexed query `(tracker_id, timestamp)`.
- If an identical reading exists, the duplicate is ignored (`IGNORED_DUPLICATE`) without raising an error or terminating the consumer.

---

## 8. Tracker `last_seen` Timestamp Policy

- When valid telemetry is accepted for an ACTIVE shipment, `tracker.last_seen` is updated to the telemetry reading's timestamp (`payload.timestamp`).
- If telemetry is rejected (no active shipment, invalid schema, unknown tracker), `tracker.last_seen` is **NOT updated**.

---

## 9. Telemetry Query API

Mounted at `GET /telemetry` (requires Bearer JWT):
- **Pagination**: `?page=1&page_size=20`.
- **Filters**: `tracker_id`, `shipment_id`, `start_time`, `end_time`.
- **Tenant Scoping**:
  - `USER`: Filtered in PostgreSQL by `organization_id = current_user.organization_id`.
  - `SUPER_ADMIN`: Cross-tenant access, with optional `?organization_id=<uuid>` filter.

---

## 10. Automated Testing Without Public Broker

Automated tests in [backend/tests/test_mqtt_telemetry.py](file:///d:/cold_chain_monitoring/backend/tests/test_mqtt_telemetry.py) execute deterministically through `ingest_telemetry_payload()`. Tests do not require network connectivity or public brokers such as `broker.emqx.io`.
