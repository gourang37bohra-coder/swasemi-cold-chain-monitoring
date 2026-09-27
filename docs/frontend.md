# Model 6: Frontend Architecture & User Interface

The SWASEMI Cold-Chain Monitoring Platform frontend provides a real-time, multi-tenant web dashboard built with React 19, TypeScript, and Vite.

---

## 1. Technology Stack

- **Core**: React 19, TypeScript 5.9, Vite
- **Routing**: `react-router-dom` (v7)
- **HTTP Client**: `axios` with global request/response interceptors
- **Mapping**: `leaflet` & `react-leaflet` with custom SVG pin markers and Polyline GPS route trails (OpenStreetMap tiles)
- **Data Visualization**: `recharts` for historical sensor telemetry (temperature, thresholds, timestamps)
- **Icons**: `lucide-react`
- **Styling**: Vanilla CSS Design System with dark-mode corporate palette, responsive card grids, accessible modals, and micro-interactions.

---

## 2. Directory Architecture

```
frontend/
├── src/
│   ├── api/
│   │   └── client.ts              # Axios instance, Bearer token interceptor, typed API endpoints
│   ├── components/
│   │   ├── Card.tsx               # Reusable styled surface container
│   │   ├── EmptyState.tsx         # Clean zero-data empty state with icon and action
│   │   ├── LoadingSpinner.tsx     # Animated loading spinner with message
│   │   ├── Modal.tsx              # Accessible dialog for CRUD and confirmations
│   │   └── StatusBadge.tsx        # Color-coded badges for Tracker & Shipment lifecycles
│   ├── context/
│   │   └── AuthContext.tsx        # Authentication state, JWT storage, /auth/me bootstrap
│   ├── hooks/
│   │   └── useLiveTelemetry.ts    # REST-backed telemetry polling hook (Model 7 WebSocket placeholder)
│   ├── layouts/
│   │   └── AppLayout.tsx          # Responsive layout: sidebar, topbar, tenant/user info, logout
│   ├── pages/
│   │   ├── Dashboard.tsx          # P0 operational view: KPI cards, live Leaflet map, recent shipments
│   │   ├── Login.tsx              # Invite-only authentication page with JWT storage
│   │   ├── Shipments.tsx          # Shipment table, create shipment modal, start/complete actions
│   │   ├── ShipmentDetail.tsx     # Recharts temperature profile, GPS route map, telemetry table
│   │   └── Trackers.tsx           # Tracker inventory, create/edit modals, delete confirmation
│   ├── router/
│   │   └── AppRouter.tsx          # ProtectedRoute, PublicRoute, and route declarations
│   ├── types/
│   │   └── index.ts               # TypeScript schemas matching FastAPI models & responses
│   ├── utils/
│   │   └── leafletIcons.ts        # SVG-based DivIcons for cross-platform Vite asset reliability
│   ├── App.tsx                    # Root provider setup
│   ├── index.css                  # Global design tokens, layout utilities, animations
│   └── main.tsx                   # Vite bootstrap entrypoint
├── .env.example                   # Environment template (VITE_API_BASE_URL)
├── package.json
├── tsconfig.json
└── vite.config.ts
```

---

## 3. Routes & Page Hierarchy

| Path | Access | Description |
| :--- | :--- | :--- |
| `/login` | Public only | Invite-only login (email/password). Redirects to `/dashboard` if authenticated. |
| `/dashboard` | Authenticated | P0 operations overview: 6 KPI metrics, Leaflet tracker map, active shipments. |
| `/trackers` | Authenticated | Paginated tracker inventory with CRUD modals and status filters. |
| `/shipments` | Authenticated | Shipment management table with lifecycle triggers (`Start`, `Complete`). |
| `/shipments/:shipmentId` | Authenticated | Deep-dive telemetry inspection, Recharts chart, Leaflet GPS route trail, and data table. |
| `*` | Any | Wildcard fallback redirecting to `/dashboard` (or `/login` if unauthenticated). |

---

## 4. Authentication Flow

1. **Invite-Only Policy**:
   - The application does not contain a public registration page.
   - User credentials and organizations are provisioned by administrators.
2. **Login Procedure (`POST /auth/login`)**:
   - Form accepts `email` and `password`.
   - On success, FastAPI returns an `access_token` and `token_type: "bearer"`.
   - The access token is persisted in `localStorage` under `swasemi_access_token`.
3. **Session Hydration (`GET /auth/me`)**:
   - Upon initial load or login, `AuthContext` requests user identity from `GET /auth/me`.
   - Hydrated fields: `id`, `email`, `organization_id`, `role` (`USER` or `SUPER_ADMIN`).
4. **Token Interception & Expiration**:
   - Every outgoing HTTP request automatically receives `Authorization: Bearer <token>`.
   - An Axios response interceptor intercepts HTTP `401 Unauthorized` responses, clears local storage, resets user state, and immediately routes the browser to `/login`.

---

## 5. API Integration & Error Handling

All network operations are centralized in `src/api/client.ts`. Response errors are normalized with domain-friendly messages:

- **401 Unauthorized**: Handled globally via Axios interceptor; triggers immediate logout and redirection to `/login`.
- **403 Forbidden**: Displays permission denial banner (e.g. attempting actions outside organization bounds).
- **404 Not Found**: Displays zero-knowledge resource missing error.
- **409 Conflict**: Displays lifecycle state error (e.g., trying to start an already active shipment).
- **422 Unprocessable Entity**: Displays structured validation error messages (e.g., invalid temperature range or negative grace readings).
- **500 Internal Server Error**: Displays a generic system error message without exposing backend stack traces.

---

## 6. Dashboard & Interactive Leaflet Map

The `/dashboard` route serves as the primary command center:

- **KPI Cards**:
  - **Active Shipments**: Current shipments in `ACTIVE` state.
  - **Active Trackers**: Trackers associated with ongoing shipments.
  - **Online Trackers**: Trackers actively sending telemetry (`ONLINE` status).
  - **Offline Trackers**: Inactive or disconnected devices (`OFFLINE` status).
  - **Latest Temperature**: Most recent reading with cold-chain safe/breach badges.
  - **Latest Telemetry Time**: Relative or absolute timestamp of the latest event.
- **Live Fleet Map**:
  - Built with `react-leaflet` and OpenStreetMap tile servers.
  - Custom SVG `divIcon` pins with dynamic status coloring (Emerald for online, Amber for warning, Slate for offline).
  - Clicking a marker opens a Leaflet popup detailing the Tracker Name, MQTT Topic, Last Seen timestamp, and latest temperature.
  - Clean empty state displayed when no telemetry or GPS coordinates exist: *"No active telemetry available"*.

---

## 7. Shipment History, Charts & GPS Trails

The `/shipments/:shipmentId` route provides granular historical analysis:

- **Temperature Profile Chart (`recharts`)**:
  - Visualizes telemetry temperature readings against elapsed time.
  - Shaded reference bands / dashed lines for minimum and maximum acceptable temperature thresholds.
  - Tooltips display temperature, humidity, battery percentage, door status, and exact UTC timestamp.
- **GPS Route Trail**:
  - Chronologically orders telemetry coordinates `(latitude, longitude)`.
  - Connects points using a Leaflet `Polyline` with custom route markers for **Start Position** (green) and **Current/Final Position** (blue).
  - Automatically fits map bounds to the recorded journey coordinates.
  - Gracefully handles stationary devices or records without GPS coordinates.
- **Telemetry Log Table**:
  - Paginated tabular view of all sensor events for regulatory auditing.

---

## 8. Role-Based Access Control (USER vs SUPER_ADMIN)

- **USER**:
  - Locked strictly to their assigned `organization_id`.
  - Sidebar and Topbar display the user's organization ID.
  - No organization-selector controls exist in the UI for regular users.
  - API requests are inherently scoped to the user's organization by the backend JWT tenant context.
- **SUPER_ADMIN**:
  - Topbar displays a prominent `SUPER_ADMIN` badge and platform-wide visibility indicator.
  - Tracker and Shipment tables display the associated `organization_id` for cross-tenant auditing.
  - Frontend architecture is decoupled and ready for dedicated Organization Administration views in subsequent phases.

---

## 9. Real-Time Placeholder (`useLiveTelemetry`)

To adhere to Model 6 boundaries, WebSockets and Redis have **not** been implemented. 

Instead, a dedicated custom React hook `useLiveTelemetry(shipmentId, trackerId, intervalMs)` is provided in `src/hooks/useLiveTelemetry.ts`:
- Currently pulls data via the REST API (`GET /telemetry`) with polite polling intervals (default: 15 seconds, adjustable or pausable).
- Exposes `{ telemetry, latestTelemetry, isLoading, error, refresh }`.
- In **Model 7**, this hook will be upgraded to subscribe to Redis/WebSocket streams without requiring structural refactoring of the consuming UI components.

---

## 10. Development & Production Build

### Prerequisites
- Node.js 18+ (tested on Node.js 22+)
- Running FastAPI backend on `http://localhost:8000`

### Setup & Startup
```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Configure environment
cp .env.example .env

# Run development server
npm run dev
```

### Production Build
```bash
npm run build
```
Build output is generated in `frontend/dist/` with type-checked bundles via `tsc -b && vite build`.
