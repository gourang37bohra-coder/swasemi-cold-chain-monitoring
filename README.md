# Cold-Chain Monitoring Platform

A multi-tenant IoT cold-chain monitoring system for tracking refrigerated shipments, sensor telemetry, and automatic temperature breach alerts.

## Project Structure
- `backend/` — FastAPI application, database configuration, Alembic migrations, domain models, authentication, MQTT ingestion, and APIs.
- `docs/` — Architecture documentation, database schema, authentication & authorization guide, API reference, and MQTT ingestion guide.
- `frontend/` — React 19, TypeScript, and Vite multi-tenant dashboard (cards, Leaflet maps, Recharts).

## Completed Models & Current Status

- **Model 1: Project Foundation & Backend Setup**
  - FastAPI service structure, PostgreSQL connectivity via psycopg v3 driver, Alembic migration framework, health check endpoints (`/health`, `/health/db`).
- **Model 2: Domain Models & Multi-Tenant Schema**
  - SQLAlchemy 2.0 models for `Organization`, `User`, `Tracker`, `Shipment`, `Telemetry`, and `Alert`.
- **Model 2 Hardening: Composite Multi-Tenant Foreign Keys**
  - Database-level defense-in-depth preventing cross-organization relationships with composite unique and foreign key constraints on `(id, organization_id)`.
- **Model 3: Authentication, JWT & Role-Based Access Control**
  - Salted bcrypt password hashing, JWT creation/decoding with claims (`sub`, `org_id`, `role`), `POST /auth/login`, `GET /auth/me`, `TenantContext` isolation, and invite-only onboarding policy.
- **Model 4: Tracker & Shipment Management APIs**
  - Full Tracker CRUD APIs (`/trackers`) and Shipment Management APIs (`/shipments`).
  - Strict shipment lifecycle state machine: `NOT_STARTED -> ACTIVE -> COMPLETED`.
  - Zero-knowledge 404 security and PostgreSQL-level pagination.
- **Model 5: MQTT Telemetry Ingestion & Active-Shipment Gating**
  - Robust telemetry ingestion pipeline via `paho-mqtt` with safe decode and error containment.
  - Strict active-shipment gating: telemetry is persisted *only* when the tracker has an `ACTIVE` shipment (`NOT_STARTED` and `COMPLETED` discard telemetry).
  - Anti-spoofing protection (organization derived strictly from PostgreSQL tracker record).
  - Application-level duplicate reading idempotency.
  - `tracker.last_seen` timestamp updating upon accepted telemetry.
  - Authenticated and tenant-scoped `GET /telemetry` query endpoint with pagination and multi-field filters.
  - Deterministic automated tests without public broker dependencies (63 total passing tests).
- **Model 6: Frontend Implementation (React + TypeScript + Vite)**
  - Full single-page application dashboard supporting multi-tenant cold-chain operations.
  - Authenticated route guards, JWT session hydration via `/auth/me`, and automatic 401 redirect.
  - Operational dashboard with 6 KPI metrics, real-time status indicators, and interactive Leaflet map.
  - Tracker management (paginated inventory, create/edit modals, delete confirmation).
  - Shipment lifecycle management (`NOT_STARTED -> ACTIVE -> COMPLETED`) with input validations.
  - Historical shipment detail view with Recharts temperature line chart, Leaflet GPS route trail, and telemetry log table.
  - Prepared `useLiveTelemetry` hook integration point for subsequent Model 7 WebSocket streaming.
- **Model 6.5: Invite-Only Onboarding & Super Admin Provisioning**
  - Tenant organization administration (`POST /admin/organizations`, `GET /admin/organizations`, `GET /admin/organizations/{id}`, `PATCH /admin/organizations/{id}`).
  - User account provisioning and management (`POST /admin/users`, `GET /admin/users`, `GET /admin/users/{id}`, `PATCH /admin/users/{id}`).
  - Strict `require_super_admin` backend authorization boundary: HTTP 403 Forbidden returned to any standard `USER`.
  - Frontend administration navigation and role-guarded views (`/organizations`, `/users`).
  - Safe user representations with zero password leakage and persistent bcrypt hashing.
  - 90 passing backend tests.
- **Model 7: Redis Pub/Sub & WebSocket Real-Time Telemetry**
  - Redis connection and lifecycle management (`RedisManager`) with connection pooling and async/sync publishing.
  - Predictable, tenant-isolated Pub/Sub channels: `coldchain:telemetry:{organization_id}`.
  - MQTT Ingestion pipeline updated: PostgreSQL persistence remains the source of truth; safe, non-blocking Redis event publishing.
  - Authenticated WebSocket endpoint: `WS /ws/telemetry?token={jwt}` with token validation, user resolution, and heartbeat ping/pong.
  - Strict tenant isolation: regular `USER` clients only receive their organization's telemetry; `SUPER_ADMIN` receives cross-tenant events.
  - Connection manager handling multiple concurrent connections, client disconnects, and graceful degradation on Redis downtime.
  - Extended health monitoring: `GET /health/redis` (returns 200 when alive, 503 when down).
  - Frontend consumption: `useLiveTelemetry` hook with exponential backoff auto-reconnect (1s–16s) dynamically updating Dashboard maps, temperatures, statuses, and Shipment detail charts and trails without page reload.
  - 108 passing backend tests.
- **Model 8: Cold-Chain Device Simulator / MQTT Device Side**
  - Autonomous device simulator located in `simulator/`, decoupled from API process.
  - Simulates 3 moving IoT trackers (`Apex Cold-Box 101`, `Medical_UnitA`, `Medical_UnitB`) plus 1 gated inactive tracker (`Apex Cold-Box 102`).
  - Realistic deterministic waypoint routes in Maharashtra logistics corridors with smooth GPS interpolation.
  - Sensor dynamics simulating temperatures within safe thresholds (or configurable excursion in `breach` mode), humidity random walk, battery depletion, and cargo door access.
  - Critical P0 Shipment Gate: queries backend REST API (`/shipments`) to dynamically bind active shipments; strictly prevents telemetry transmission when no active shipment is running.
  - Connected and verified end-to-end against public broker `broker.emqx.io:1883`.
  - 117 passing backend and simulator tests; frontend production build succeeds with 0 errors.

## Frontend Startup

```bash
# Navigate to the frontend directory
cd frontend

# Install dependencies
npm install

# Start Vite development server
npm run dev
```

To build for production:
```bash
npm run build
```
