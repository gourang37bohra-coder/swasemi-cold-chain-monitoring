"""Authentication, JWT, RBAC, and Tenant Context tests for Phase 3."""

from datetime import timedelta
import uuid
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth_deps import TenantContext, require_super_admin
from app.core.database import engine
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.main import app
from app.models.organization import Organization
from app.models.user import User, UserRole


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture
def client():
    """TestClient for FastAPI app."""
    return TestClient(app)


@pytest.fixture
def db_session():
    """Provides a database session for creating test fixtures with auto-cleanup."""
    connection = engine.connect()
    session = Session(bind=connection)
    created_org_ids = []
    created_user_ids = []

    yield session, created_org_ids, created_user_ids

    # Cleanup any entities created during test
    if created_user_ids:
        session.query(User).filter(User.id.in_(created_user_ids)).delete(synchronize_session=False)
        session.commit()
    if created_org_ids:
        session.query(Organization).filter(Organization.id.in_(created_org_ids)).delete(synchronize_session=False)
        session.commit()

    session.close()
    connection.close()


@pytest.fixture
def sample_org(db_session):
    session, created_org_ids, _ = db_session
    org = Organization(name=f"AuthTestOrg-{uuid.uuid4().hex[:8]}")
    session.add(org)
    session.commit()
    session.refresh(org)
    created_org_ids.append(org.id)
    return org


@pytest.fixture
def sample_user(db_session, sample_org):
    session, _, created_user_ids = db_session
    email = f"user-{uuid.uuid4().hex[:8]}@example.com"
    raw_password = "SecurePassword123!"
    user = User(
        email=email,
        password_hash=hash_password(raw_password),
        organization_id=sample_org.id,
        role=UserRole.USER,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    created_user_ids.append(user.id)
    return user, raw_password


@pytest.fixture
def sample_super_admin(db_session):
    session, _, created_user_ids = db_session
    email = f"admin-{uuid.uuid4().hex[:8]}@platform.com"
    raw_password = "SuperAdminPassword123!"
    admin = User(
        email=email,
        password_hash=hash_password(raw_password),
        organization_id=None,
        role=UserRole.SUPER_ADMIN,
    )
    session.add(admin)
    session.commit()
    session.refresh(admin)
    created_user_ids.append(admin.id)
    return admin, raw_password


# ──────────────────────────────────────────────
# 1. Invite-Only Policy & Public Registration Disabled Tests
# ──────────────────────────────────────────────

def test_public_registration_endpoint_unavailable(client: TestClient, sample_org: Organization):
    """Compliance Test: Public sign-up is disabled; platform is strictly invite-only."""
    response = client.post(
        "/auth/register",
        json={
            "email": f"unauthorized-{uuid.uuid4().hex[:8]}@example.com",
            "password": "Password123!",
            "organization_id": str(sample_org.id),
        },
    )
    # The public registration route must not exist (404 Not Found)
    assert response.status_code in (404, 405)


def test_password_hashing_and_verification():
    """Unit test for bcrypt password hashing and verification."""
    plain = "MySecretPassword123!"
    hashed = hash_password(plain)

    # Never store plaintext
    assert hashed != plain
    # Must use bcrypt format
    assert hashed.startswith("$2b$") or hashed.startswith("$2a$")

    # Correct password succeeds
    assert verify_password(plain, hashed) is True
    # Incorrect password fails
    assert verify_password("WrongPassword!", hashed) is False


def test_password_stored_as_bcrypt_hash_in_db(db_session, sample_org: Organization):
    """Verify that stored user accounts have bcrypt hashes in the database."""
    session, _, created_user_ids = db_session
    raw_password = "PlaintextSecret987!"
    user = User(
        email=f"hashcheck-{uuid.uuid4().hex[:8]}@coldchain.com",
        password_hash=hash_password(raw_password),
        organization_id=sample_org.id,
        role=UserRole.USER,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    created_user_ids.append(user.id)

    # Check direct database state
    user_in_db = session.scalar(select(User).where(User.id == user.id))
    assert user_in_db is not None
    assert user_in_db.password_hash != raw_password
    assert user_in_db.password_hash.startswith("$2b$") or user_in_db.password_hash.startswith("$2a$")
    assert verify_password(raw_password, user_in_db.password_hash) is True


# ──────────────────────────────────────────────
# 2. Login Tests
# ──────────────────────────────────────────────

def test_login_success(client: TestClient, sample_user):
    user, raw_password = sample_user
    response = client.post(
        "/auth/login",
        json={"email": user.email, "password": raw_password},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"].lower() == "bearer"
    assert "password_hash" not in data


def test_login_invalid_password_rejected(client: TestClient, sample_user):
    user, _ = sample_user
    response = client.post(
        "/auth/login",
        json={"email": user.email, "password": "WrongPassword123!"},
    )
    assert response.status_code == 401
    assert "invalid email or password" in response.json()["detail"].lower()


def test_login_unknown_email_rejected(client: TestClient):
    response = client.post(
        "/auth/login",
        json={"email": "nonexistent@coldchain.com", "password": "AnyPassword123!"},
    )
    assert response.status_code == 401
    assert "invalid email or password" in response.json()["detail"].lower()


# ──────────────────────────────────────────────
# 3. JWT Claims Verification
# ──────────────────────────────────────────────

def test_jwt_claims_structure_user(client: TestClient, sample_user):
    user, raw_password = sample_user
    response = client.post(
        "/auth/login",
        json={"email": user.email, "password": raw_password},
    )
    token = response.json()["access_token"]
    payload = decode_access_token(token)

    assert payload["sub"] == str(user.id)
    assert payload["org_id"] == str(user.organization_id)
    assert payload["role"] == "USER"
    assert "exp" in payload
    assert "iat" in payload
    assert "password" not in payload
    assert "password_hash" not in payload


def test_jwt_claims_structure_super_admin(client: TestClient, sample_super_admin):
    admin, raw_password = sample_super_admin
    response = client.post(
        "/auth/login",
        json={"email": admin.email, "password": raw_password},
    )
    token = response.json()["access_token"]
    payload = decode_access_token(token)

    assert payload["sub"] == str(admin.id)
    assert payload["org_id"] is None
    assert payload["role"] == "SUPER_ADMIN"
    assert "exp" in payload


# ──────────────────────────────────────────────
# 4. Current User (/auth/me) Tests
# ──────────────────────────────────────────────

def test_get_me_success_user(client: TestClient, sample_user):
    user, raw_password = sample_user
    login_res = client.post(
        "/auth/login",
        json={"email": user.email, "password": raw_password},
    )
    token = login_res.json()["access_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()

    assert data["id"] == str(user.id)
    assert data["email"] == user.email
    assert data["organization_id"] == str(user.organization_id)
    assert data["role"] == "USER"
    assert "password_hash" not in data


def test_get_me_success_super_admin(client: TestClient, sample_super_admin):
    admin, raw_password = sample_super_admin
    login_res = client.post(
        "/auth/login",
        json={"email": admin.email, "password": raw_password},
    )
    token = login_res.json()["access_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()

    assert data["id"] == str(admin.id)
    assert data["email"] == admin.email
    assert data["organization_id"] is None
    assert data["role"] == "SUPER_ADMIN"
    assert "password_hash" not in data


def test_get_me_missing_token_rejected(client: TestClient):
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_get_me_malformed_token_rejected(client: TestClient):
    response = client.get(
        "/auth/me", headers={"Authorization": "Bearer this-is-not-a-valid-token"}
    )
    assert response.status_code == 401


def test_get_me_expired_token_rejected(client: TestClient, sample_user):
    user, _ = sample_user
    # Create an expired token by setting negative expires_delta
    expired_token = create_access_token(
        user_id=user.id,
        org_id=user.organization_id,
        role=user.role.value,
        expires_delta=timedelta(seconds=-10),
    )

    response = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert response.status_code == 401


# ──────────────────────────────────────────────
# 5. Tenant Authorization & Context Tests
# ──────────────────────────────────────────────

def test_tenant_context_user_isolation(db_session):
    session, created_org_ids, created_user_ids = db_session

    org_a = Organization(name=f"OrgA-{uuid.uuid4().hex[:8]}")
    org_b = Organization(name=f"OrgB-{uuid.uuid4().hex[:8]}")
    session.add_all([org_a, org_b])
    session.commit()
    created_org_ids.extend([org_a.id, org_b.id])

    user_a = User(
        email=f"usera-{uuid.uuid4().hex[:8]}@a.com",
        password_hash="hash",
        organization_id=org_a.id,
        role=UserRole.USER,
    )
    user_b = User(
        email=f"userb-{uuid.uuid4().hex[:8]}@b.com",
        password_hash="hash",
        organization_id=org_b.id,
        role=UserRole.USER,
    )
    session.add_all([user_a, user_b])
    session.commit()
    created_user_ids.extend([user_a.id, user_b.id])

    context_a = TenantContext(user_a)
    context_b = TenantContext(user_b)

    # User A operating on Org A resource -> allowed
    context_a.assert_same_organization(org_a.id)

    # User A operating on Org B resource -> denied with 403
    with pytest.raises(HTTPException) as exc_info:
        context_a.assert_same_organization(org_b.id)
    assert exc_info.value.status_code == 403

    # User B operating on Org B resource -> allowed
    context_b.assert_same_organization(org_b.id)

    # User B operating on Org A resource -> denied with 403
    with pytest.raises(HTTPException) as exc_info:
        context_b.assert_same_organization(org_a.id)
    assert exc_info.value.status_code == 403


def test_tenant_context_super_admin_cross_org(db_session):
    session, created_org_ids, created_user_ids = db_session

    org_a = Organization(name=f"OrgA-{uuid.uuid4().hex[:8]}")
    org_b = Organization(name=f"OrgB-{uuid.uuid4().hex[:8]}")
    session.add_all([org_a, org_b])
    session.commit()
    created_org_ids.extend([org_a.id, org_b.id])

    admin = User(
        email=f"admin-{uuid.uuid4().hex[:8]}@platform.com",
        password_hash="hash",
        organization_id=None,
        role=UserRole.SUPER_ADMIN,
    )
    session.add(admin)
    session.commit()
    created_user_ids.append(admin.id)

    admin_context = TenantContext(admin)

    # Super Admin can access Org A and Org B without 403
    admin_context.assert_same_organization(org_a.id)
    admin_context.assert_same_organization(org_b.id)


def test_require_super_admin_dependency(sample_user, sample_super_admin):
    import asyncio

    user, _ = sample_user
    admin, _ = sample_super_admin

    # Normal user should be rejected with 403
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_super_admin(current_user=user))
    assert exc.value.status_code == 403
    assert "super-admin privileges required" in exc.value.detail.lower()

    # Super admin should pass through
    result = asyncio.run(require_super_admin(current_user=admin))
    assert result.id == admin.id
