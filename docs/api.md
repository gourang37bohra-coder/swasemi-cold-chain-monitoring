# Cold-Chain Monitoring Platform — API Reference (Model 4)

This document specifies the Tracker Management and Shipment Management APIs implemented in Model 4 of the SWASEMI Cold-Chain Monitoring Platform.

---

## 1. Authentication & Tenant Isolation Rules

All endpoints documented below require a valid JSON Web Token passed in the HTTP Authorization header:
```http
Authorization: Bearer <access_token>
```

### Role-Based Behavior
- **`USER`**:
  - Bound strictly to their own organization (`organization_id`).
  - Query filtering is enforced directly in PostgreSQL (`WHERE organization_id = current_user.organization_id`).
  - Cannot specify or override `organization_id` in request payloads or query parameters.
  - Returns `404 Not Found` (zero-knowledge) when attempting to access another organization's resources, preventing information leakage.
- **`SUPER_ADMIN`**:
  - Has platform-wide cross-tenant access.
  - Can view and manage trackers and shipments across all organizations.
  - Can optionally filter lists by `?organization_id=<uuid>`.
  - Must specify `organization_id` when creating trackers.

---

## 2. Pagination

List endpoints support standard cursor/offset query parameters:

| Parameter | Type | Default | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- |
| `page` | `int` | `1` | `ge=1` | 1-indexed page number |
| `page_size` | `int` | `20` | `ge=1, le=100` | Number of items per page |

### Paginated Response Structure
```json
{
  "items": [ ... ],
  "page": 1,
  "page_size": 20,
  "total": 45
}
```

---

## 3. Tracker Endpoints

Mounted at `/trackers`.

### A. Create Tracker: `POST /trackers`
- **Request Body**:
  ```json
  {
    "name": "Fridge-Unit-North-01",
    "mqtt_topic": "devices/tracker-north-01/telemetry",
    "status": "OFFLINE",
    "organization_id": "optional-for-superadmin-uuid"
  }
  ```
- **Validation**:
  - `name`: Required (non-empty string, max 255 chars).
  - `mqtt_topic`: Required (non-empty string, max 255 chars).
  - `status`: Optional, defaults to `"OFFLINE"`. Allowed: `"ONLINE"`, `"OFFLINE"`.
  - For `USER`: Organization is resolved strictly from user context.
  - For `SUPER_ADMIN`: `organization_id` is required in the body and must exist in the database.
- **Response** (`HTTP 201 Created`): Returns full `TrackerResponse`.

### B. List Trackers: `GET /trackers`
- **Query Parameters**: `page`, `page_size`, `organization_id` (SUPER_ADMIN only).
- **Behavior**:
  - Filters strictly by tenant for normal users.
  - Executes count and pagination directly in PostgreSQL.
- **Response** (`HTTP 200 OK`): `PaginatedTrackersResponse`.

### C. Get Tracker: `GET /trackers/{tracker_id}`
- **Response** (`HTTP 200 OK`): `TrackerResponse`.
- **Error**: Returns `HTTP 404 Not Found` if tracker does not exist or belongs to another organization.

### D. Update Tracker: `PATCH /trackers/{tracker_id}`
- **Request Body**: Partial update (`name`, `mqtt_topic`, `status`).
- **Response** (`HTTP 200 OK`): Updated `TrackerResponse`.
- **Error**: Returns `HTTP 404 Not Found` if tracker does not exist or belongs to another organization.

### E. Delete Tracker: `DELETE /trackers/{tracker_id}`
- **Behavior**: Enforces database `RESTRICT` constraints.
- **Response**: `HTTP 204 No Content` on successful deletion.
- **Error**: Returns `HTTP 409 Conflict` if the tracker has associated shipments or telemetry records.

---

## 4. Shipment Endpoints & Lifecycle

Mounted at `/shipments`.

### Shipment Lifecycle State Machine

```
   [ NOT_STARTED ] ──( POST /shipments/{id}/start )──▶ [ ACTIVE ] ──( POST /shipments/{id}/complete )──▶ [ COMPLETED ]
```

- **`NOT_STARTED`**: Initial state upon creation. `started_at` is `null`, `ended_at` is `null`.
- **`ACTIVE`**: Shipment in transit. `started_at` set to current UTC timestamp.
- **`COMPLETED`**: Shipment finished. `ended_at` set to current UTC timestamp.
- **Invalid Transitions**:
  - `NOT_STARTED -> COMPLETED` (Rejected: 409 Conflict)
  - `ACTIVE -> ACTIVE` (Rejected: 409 Conflict)
  - `COMPLETED -> ACTIVE` / `COMPLETED -> COMPLETED` (Rejected: 409 Conflict)

### A. Create Shipment: `POST /shipments`
- **Request Body**:
  ```json
  {
    "tracker_id": "4b684cb3-0b0f-488f-9a4f-69ff32a514d7",
    "minimum_temperature": 2.0,
    "maximum_temperature": 8.0,
    "grace_readings": 3
  }
  ```
- **Validation**:
  - `minimum_temperature < maximum_temperature` (strictly enforced; returns 422 if invalid).
  - `grace_readings >= 1` (returns 422 if < 1).
  - Assigned tracker must exist and belong to the requesting user's organization. Cross-organization tracker assignment is rejected with `404 Not Found`.
- **Initial State**:
  - `status`: `"NOT_STARTED"`
  - `started_at`: `null`
  - `ended_at`: `null`
  - `breach_active`: `false`
- **Response** (`HTTP 201 Created`): `ShipmentResponse`.

### B. List Shipments: `GET /shipments`
- **Query Parameters**: `page`, `page_size`, `organization_id` (SUPER_ADMIN only).
- **Behavior**: Tenant-filtered in PostgreSQL for `USER`.
- **Response** (`HTTP 200 OK`): `PaginatedShipmentsResponse`.

### C. Get Shipment: `GET /shipments/{shipment_id}`
- **Response** (`HTTP 200 OK`): `ShipmentResponse`.
- **Error**: Returns `HTTP 404 Not Found` if shipment does not exist or belongs to another organization.

### D. Start Shipment: `POST /shipments/{shipment_id}/start`
- **Requirement**: Current status must be `NOT_STARTED`.
- **State Change**: Sets `status = ACTIVE`, sets `started_at = utcnow()`.
- **Response** (`HTTP 200 OK`): Updated `ShipmentResponse`.
- **Error**: Returns `HTTP 409 Conflict` if shipment status is not `NOT_STARTED`.

### E. Complete Shipment: `POST /shipments/{shipment_id}/complete`
- **Requirement**: Current status must be `ACTIVE`.
- **State Change**: Sets `status = COMPLETED`, sets `ended_at = utcnow()`.
- **Response** (`HTTP 200 OK`): Updated `ShipmentResponse`.
- **Error**: Returns `HTTP 409 Conflict` if shipment status is not `ACTIVE`.
