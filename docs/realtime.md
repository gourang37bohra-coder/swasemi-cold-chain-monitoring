# Real-Time Telemetry Architecture (Model 7)

## Overview

Model 7 integrates **Redis Pub/Sub** and **WebSockets** into the SWASEMI Cold-Chain Monitoring Platform to provide low-latency live telemetry delivery to connected browser clients without polling.

```
MQTT (Broker)
     │
     ▼
FastAPI Ingestion
     ├──────────────────────► PostgreSQL (Historical source of truth)
     │
     └──────────────────────► Redis Pub/Sub (Event bus: coldchain:telemetry:{org_id})
                                     │
                                     ▼
                              WebSocket Layer (Tenant-filtered bridge)
                                     │
                                     ▼
                                React UI (Live updates without reload)
```

---

## 1. Redis Role & Lifecycle

- **Role**: Redis operates strictly as an in-memory, decoupled real-time event bus. It does NOT store or replace historical telemetry.
- **Connection Management**: 
  - Managed by `RedisManager` (`backend/app/realtime/redis.py`).
  - Async connection pool initialized during FastAPI startup (`lifespan`) and closed gracefully during shutdown.
  - No connections are created or destroyed per telemetry message.
  - Thread-safe synchronous publish (`publish_sync`) is provided for MQTT callback threads.
- **Configuration**:
  - `REDIS_URL` in `backend/.env` (default: `redis://localhost:6379/0`).
  - Health check available at `GET /health/redis`.

---

## 2. Telemetry Channel Structure

Redis channels are scoped per tenant to prevent cross-organization event leakage at the transport layer:

```
coldchain:telemetry:{organization_id}
```

Example:
`coldchain:telemetry:36817a3b-0bfe-4577-a647-da8325322448`

- The `organization_id` is resolved server-side from the trusted tracker record in PostgreSQL during MQTT ingestion.
- Client-supplied channel names or organization parameters are strictly disallowed.

---

## 3. MQTT → PostgreSQL → Redis Ingestion Flow

1. Telemetry payload arrives via MQTT (`swasemi/coldchain/telemetry/{tracker_id}`).
2. Payload is validated with `TelemetryCreatePayload`.
3. Tracker is looked up in PostgreSQL.
4. Active shipment check is performed (must be `ACTIVE`).
5. **PostgreSQL Persistence**: Telemetry is committed to the database first.
6. **Redis Publication**:
   - Telemetry event is serialized into a clean, safe JSON dictionary.
   - Published to `coldchain:telemetry:{tracker.organization_id}`.
7. **Failure Isolation**: If Redis is unreachable, an error is logged, but the database transaction remains committed and the MQTT ingestion succeeds. Telemetry data is never lost due to Redis downtime.

---

## 4. WebSocket Endpoint & Authentication

### Endpoint
```
WS /ws/telemetry?token={jwt_token}
```

### Authentication & Handshake
1. Browser opens a WebSocket connection passing the access token in the query parameter (`?token=...`).
2. Server validates the JWT signature and expiration using existing security utilities (`verify_token`).
3. User is resolved from the database; deactivated users are rejected with status code `4003 Forbidden`.
4. Invalid or expired tokens are rejected with status code `4001 Unauthorized`.
5. Upon successful verification, the server sends a welcome message:
   ```json
   {
     "type": "connection.established",
     "user_id": "...",
     "organization_id": "...",
     "role": "USER"
   }
   ```

---

## 5. Tenant Isolation

- **Regular Users (`USER`)**:
  - Bound exclusively to their own `organization_id` derived from their authenticated database profile.
  - Only receive events published to `coldchain:telemetry:{user.organization_id}`.
  - Any client parameter attempting to access another organization is ignored.
- **Super Administrators (`SUPER_ADMIN`)**:
  - Authorized for platform-wide monitoring.
  - Receive telemetry across all tenant channels.

---

## 6. Message Format

Telemetry messages forwarded to WebSocket clients follow a structured JSON schema:

```json
{
  "type": "telemetry.updated",
  "data": {
    "tracker_id": "11111111-1111-1111-1111-111111111111",
    "shipment_id": "22222222-2222-2222-2222-222222222222",
    "temperature": 4.5,
    "battery_pct": 94,
    "latitude": 19.0760,
    "longitude": 72.8777,
    "timestamp": "2026-09-27T10:00:00Z"
  }
}
```

No internal database credentials, user secrets, or SQLAlchemy state are ever serialized or transmitted.

---

## 7. Heartbeat & Keepalive

- Clients send `{ "type": "ping" }` or WebSocket standard ping frames.
- Server responds with `{ "type": "pong" }`.
- Background task periodically broadcasts ping to detect and clean up dead or zombie sockets safely without crashing the server.

---

## 8. Frontend Reconnect Strategy

The frontend hook (`frontend/src/hooks/useLiveTelemetry.ts`) implements robust reconnect logic:
- **Exponential Backoff**: Reconnect delays start at 1000ms and double up to a maximum of 16000ms:
  `1s → 2s → 4s → 8s → 16s`
- **Backoff Reset**: Reconnect counter resets to 1000ms immediately upon a successful connection handshake.
- **Fresh Authentication**: Each reconnect attempt reads the latest valid access token from `AuthContext` to prevent reconnection loops with stale or expired credentials.
- **Component Consumption**:
  - `Dashboard`: Dynamically moves tracker markers on the Leaflet map and updates live temperatures and online/offline statuses.
  - `ShipmentDetail`: Appends new readings to the Recharts temperature timeline and extends the GPS trail in real time without refreshing the page.

---

## 9. Failure Behavior & Resilience

| Scenario | System Behavior |
| :--- | :--- |
| **Redis Server Down** | Telemetry ingestion to PostgreSQL continues uninterrupted. Telemetry history is preserved. Redis health check returns `503`. |
| **WebSocket Client Disconnects** | Safe removal from connection manager; no unhandled exceptions or leaks in the telemetry pipeline. |
| **Network Interruption** | Browser detects socket closure and triggers automatic reconnect with exponential backoff. |
| **Expired JWT on Reconnect** | WebSocket handshake fails with `4001`; client redirects or triggers token refresh. |
