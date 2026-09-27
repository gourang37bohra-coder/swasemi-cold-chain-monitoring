# Authentication, JWT, and Multi-Tenant Authorization Foundation

This document specifies the authentication system and role-based / tenant-aware authorization architecture implemented in Phase 3 of the SWASEMI Cold-Chain Monitoring Platform.

---

## 1. Architecture Overview

Phase 3 introduces stateless JWT-based authentication alongside a strict tenant isolation foundation:

```
[ Client Request ]
       │
       ▼ Authorization: Bearer <JWT>
[ HTTPBearer Scheme (app/core/auth_deps.py) ]
       │
       ▼ Validate Signature & Expiration (app/core/security.py)
[ Claims Verification: sub, role, org_id ]
       │
       ▼ Database User Resolution (app/models/user.py)
[ User Exists? Role Matches? Org Matches? ]
       │
       ▼ Pass User & TenantContext
[ Handler / API Route ]
```

---

## 2. Password Hashing

- **Algorithm**: `bcrypt` using salted hashes generated via `bcrypt.gensalt()`.
- **Implementation**: [backend/app/core/security.py](file:///d:/cold_chain_monitoring/backend/app/core/security.py)
  - `hash_password(plain_password: str) -> str`: Produces a one-way `$2b$` bcrypt hash.
  - `verify_password(plain_password: str, password_hash: str) -> bool`: Constant-time hash verification.
- **Security Guarantees**:
  - Plaintext passwords are never persisted to PostgreSQL.
  - Plaintext passwords and hashes are never emitted in logs.
  - `password_hash` is explicitly excluded from all Pydantic response schemas (`UserResponse`, `TokenResponse`).

---

## 3. JWT Token Architecture

- **Format**: Signed JSON Web Token (`HS256` default).
- **Configuration**:
  - `JWT_SECRET_KEY`: Configured via environment variable (`backend/.env`). A default development key is provided; production requires a high-entropy secret.
  - `JWT_ALGORITHM`: Configured via environment variable (default: `HS256`).
  - `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`: Configured via environment variable (default: `60` minutes).
- **Claims Payload**:
  ```json
  {
    "sub": "3d347ddf-9c4f-4594-a492-dee25eb07aa4",
    "org_id": "fe2340b4-3d8d-4fcd-9cce-921576904846",
    "role": "USER",
    "iat": 1727357400,
    "exp": 1727361000
  }
  ```
  - `sub`: Unique UUID string of the authenticated user.
  - `org_id`: UUID string of the user's organization (`null` for `SUPER_ADMIN`).
  - `role`: Role string (`"USER"` or `"SUPER_ADMIN"`).
  - `iat`: Timestamp (UTC) when the token was issued.
  - `exp`: Timestamp (UTC) when the token expires.
- **Validation Rules**:
  - Expired tokens are rejected with HTTP 401.
  - Malformed tokens or tokens with an invalid signature are rejected with HTTP 401.
  - Tokens missing `sub` or `role` are rejected with HTTP 401.
  - Token contents are never printed to logs.

---

## 4. Endpoints & Onboarding Policy

### Invite-Only Onboarding Policy
The platform strictly enforces **invite-only / admin-provisioned onboarding**:
- There is **no public self-registration**.
- Public requests to `/auth/register` return `HTTP 404 Not Found`.
- Only a `SUPER_ADMIN` can create organizations and provision users (administrative functionality).
- Normal `USER` accounts can only log in once provisioned.

The active authentication router is mounted at prefix `/auth`:

### B. User Login: `POST /auth/login`
- **Request Body**:
  ```json
  {
    "email": "operator@biopharma.com",
    "password": "StrongPassword123!"
  }
  ```
- **Behavior**:
  - Finds user by email and validates bcrypt password hash.
  - Employs a generic error message (`"Invalid email or password."`) with HTTP 401 for both unknown emails and incorrect passwords to prevent user-enumeration attacks.
- **Response** (`HTTP 200 OK`):
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer"
  }
  ```

### C. Current Authenticated User: `GET /auth/me`
- **Headers**: `Authorization: Bearer <access_token>`
- **Behavior**:
  - Decodes and validates JWT signature, expiration, and claims.
  - Resolves user from database; verifies role match and org_id match.
- **Response** (`HTTP 200 OK`):
  ```json
  {
    "id": "3d347ddf-9c4f-4594-a492-dee25eb07aa4",
    "email": "operator@biopharma.com",
    "organization_id": "fe2340b4-3d8d-4fcd-9cce-921576904846",
    "role": "USER",
    "created_at": "2026-09-26T18:50:10.275921Z"
  }
  ```

---

## 5. Multi-Tenant Authorization Foundation

The foundation is built in [backend/app/core/auth_deps.py](file:///d:/cold_chain_monitoring/backend/app/core/auth_deps.py):

### Roles
1. **`USER`**:
   - Belongs to exactly one organization (`organization_id` is required).
   - Injected into routes via `TenantContext`.
   - `TenantContext.assert_same_organization(resource_org_id)` raises `HTTP 403 Forbidden` if `resource_org_id != user.organization_id`.
   - Cannot tamper with or override tenant scope via query or path parameters.
2. **`SUPER_ADMIN`**:
   - Platform-wide administrative user (`organization_id` is `null`).
   - `TenantContext.assert_same_organization(resource_org_id)` allows cross-organization access unconditionally.
   - Protected routes can require this role using `require_super_admin` dependency.

---

## 6. Error Handling Summary

| Scenario | HTTP Status | Response Detail |
| :--- | :--- | :--- |
| Missing Authorization header | `401 Unauthorized` | `"Invalid or missing authentication credentials."` |
| Malformed / invalid signature JWT | `401 Unauthorized` | `"Invalid or missing authentication credentials."` |
| Expired JWT | `401 Unauthorized` | `"Invalid or missing authentication credentials."` |
| Wrong login password | `401 Unauthorized` | `"Invalid email or password."` |
| Non-existent email on login | `401 Unauthorized` | `"Invalid email or password."` |
| Duplicate email on registration | `409 Conflict` | `"An account with this email already exists."` |
| Non-existent organization on registration | `422 Unprocessable` | `"Organization not found."` |
| Password < 8 characters | `422 Unprocessable` | Validation error message |
| Cross-tenant resource access attempt | `403 Forbidden` | `"Access to this resource is not permitted."` |
| Regular user accessing super-admin route | `403 Forbidden` | `"Super-admin privileges required."` |

---

## 7. Scope & Roadmap

### Implemented & Verified
- [x] PyJWT and bcrypt integration
- [x] Password hashing and constant-time verification
- [x] Strict invite-only onboarding policy (public `/auth/register` permanently disabled)
- [x] `POST /auth/login` with enumeration defense
- [x] `GET /auth/me` current user profile
- [x] `get_current_user`, `TenantContext`, `require_super_admin` dependencies
- [x] Model 6.5 Super Admin Tenant & User Provisioning (`/admin/organizations`, `/admin/users`) — see [docs/administration.md](file:///d:/cold_chain_monitoring/docs/administration.md)
- [x] Comprehensive test suite (90 total passing tests)

