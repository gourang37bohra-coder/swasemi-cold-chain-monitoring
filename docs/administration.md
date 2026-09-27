# Model 6.5: Administration & Invite-Only Onboarding Architecture

This document specifies the administrative provisioning workflows, organization management, and tenant user onboarding implemented in Model 6.5 of the SWASEMI Cold-Chain Monitoring Platform.

---

## 1. Overview & Invite-Only Policy

The SWASEMI platform enforces a strict **invite-only onboarding model**:
- **NO Public Registration**: There is no self-service sign-up or registration endpoint (`POST /auth/register` is permanently disabled).
- **Controlled Tenant Provisioning**: Only authenticated users with the `SUPER_ADMIN` role can create client tenant organizations and provision operator accounts.
- **Tenant Scoping**: Regular `USER` accounts are bound strictly to their provisioned `organization_id` and have zero access to administrative endpoints or other organizations' assets.

```
                  ┌────────────────────────┐
                  │      SUPER_ADMIN       │
                  └───────────┬────────────┘
                              │
          ┌───────────────────┴───────────────────┐
          ▼                                       ▼
┌────────────────────────┐             ┌────────────────────────┐
│  Create Organization   │             │   Provision New USER   │
│ POST /admin/orgs       │             │   POST /admin/users    │
└────────────────────────┘             └───────────┬────────────┘
                                                   │
                                                   ▼
                                       ┌────────────────────────┐
                                       │   USER Logs in         │
                                       │   POST /auth/login     │
                                       └───────────┬────────────┘
                                                   │
                                                   ▼
                                       ┌────────────────────────┐
                                       │ Tenant-Isolated Access │
                                       │ (Dashboard / Trackers) │
                                       └────────────────────────┘
```

---

## 2. Admin Authorization & Security Boundary

All administration endpoints require:
1. A valid, unexpired Bearer JWT token.
2. The authenticated user must hold `role: SUPER_ADMIN`.

### Enforcement Mechanism
Authorization is enforced in FastAPI through the `require_super_admin` dependency:
```python
router = APIRouter(
    prefix="/admin",
    tags=["Administration"],
    dependencies=[Depends(require_super_admin)],
)
```
- **Unauthenticated requests** receive `401 Unauthorized`.
- **Regular `USER` accounts** receive `403 Forbidden` (`detail: "Super-admin privileges required."`).
- Frontend visibility controls (hiding menu items or redirecting routes) exist solely for UX. FastAPI remains the definitive security boundary.

---

## 3. Organization Management API

### Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/admin/organizations` | Creates a new tenant organization. Enforces name uniqueness. |
| `GET` | `/admin/organizations` | Paginated list of organizations including real-time `user_count`. |
| `GET` | `/admin/organizations/{id}` | Retrieves a single organization by UUID with `user_count`. |
| `PATCH`| `/admin/organizations/{id}` | Updates organization name (validates uniqueness). |

### Create Organization
- **Request Body**:
  ```json
  {
    "name": "Apex Pharma Global"
  }
  ```
- **Rules**:
  - `name`: 1–255 characters, stripped of leading/trailing whitespace.
  - The database generates a server-side UUID (`uuid.uuid4()`); client-supplied IDs are never accepted.
  - If an organization with the same name already exists, the API returns `409 Conflict`.
- **Response**:
  ```json
  {
    "id": "36817a3b-0bfe-4577-a647-da8325232448",
    "name": "Apex Pharma Global",
    "created_at": "2026-09-27T10:00:00Z",
    "updated_at": "2026-09-27T10:00:00Z",
    "user_count": 0
  }
  ```

---

## 4. User Provisioning API

### Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/admin/users` | Provisions a new user account under an organization. |
| `GET` | `/admin/users` | Lists users with server-side filters (`organization_id`, `role`, `email`). |
| `GET` | `/admin/users/{id}` | Retrieves a single user by UUID. Safe fields only. |
| `PATCH`| `/admin/users/{id}` | Updates user role, organization assignment, or password. |

### Provisioning Rules & Invariants
1. **Email Uniqueness**: Verified against the `users` table; duplicates return `409 Conflict`.
2. **Organization Requirement**:
   - Accounts with `role: "USER"` **must** supply a valid `organization_id`. If missing, returns `422 Unprocessable Entity`. If the organization UUID does not exist, returns `404 Not Found`.
   - Accounts with `role: "SUPER_ADMIN"` are platform-wide; `organization_id` is set to `null`.
3. **Password Security**:
   - Minimum password length is 8 characters.
   - Passwords are immediately salted and hashed with `bcrypt.gensalt()`.
   - Plaintext passwords are never persisted to PostgreSQL or written to logs.
   - Responses never include `password_hash`.
4. **Administrative Protection**:
   - When modifying user roles via `PATCH /admin/users/{id}`, the API prevents demoting the last remaining `SUPER_ADMIN` to ensure administrative continuity.

---

## 5. Frontend Administration UI

The React/TypeScript frontend exposes a dedicated **Administration** module available only to `SUPER_ADMIN` accounts.

### Navigation Structure
- When logged in as `SUPER_ADMIN`:
  - **Sidebar**: Displays an **Administration** section with links to **Organizations** (`/organizations`) and **Users** (`/users`).
  - **Topbar**: Displays the elevated amber badge: `Platform Admin Mode (Cross-Tenant Scope)`.
- When logged in as `USER`:
  - The Administration section is completely omitted from the DOM.
  - The topbar displays: `Organization Scoped Tenant`.

### Route Protection (`AdminRoute`)
- In `src/router/AppRouter.tsx`, both `/organizations` and `/users` are wrapped with `<AdminRoute>`.
- If an unprivileged user navigates directly to `/organizations` or `/users`, they are immediately redirected to `/dashboard`.

### Pages
1. **Organizations (`/organizations`)**:
   - Tabular view: Organization Name, UUID, User Count, Created Date.
   - **+ Create Organization** Modal: Validates name, displays backend conflict errors (409) if duplicate.
   - **Rename** action: Allows updating organization display names.
2. **Users (`/users`)**:
   - Filter toolbar: Search by email, filter by Role (`USER` / `SUPER_ADMIN`), and filter by Organization.
   - Tabular view: Email, Role Badge, Assigned Organization, Created Date.
   - **+ Create User** Modal: Dynamic organization dropdown fetched via `GET /admin/organizations`, email and password validation, role selector.
   - **Edit User** Modal: Modify organization, adjust role, or set a new password (never shows stored password or hash).

---

## 6. Verification & Automated Tests

A dedicated test suite in `tests/test_admin.py` verifies all administrative features:
- Organization creation, listing, retrieval, renaming, and conflict handling.
- User creation, email uniqueness, bcrypt hash verification, and login flow.
- 403 Forbidden enforcement on regular `USER` accounts across all `/admin` routes.
- Protection against demoting the last platform super-admin.
- 90 total backend tests passing.
- Frontend builds cleanly via `npm run build` without TypeScript errors.
