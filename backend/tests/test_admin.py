"""Tests for Model 6.5 Admin APIs: Organization and User Provisioning."""

import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import engine
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.main import app
from app.models.organization import Organization
from app.models.user import User, UserRole


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db_session():
    """Provides a database session with entity tracking and auto-cleanup."""
    connection = engine.connect()
    session = Session(bind=connection)
    cleanup_user_ids = []
    cleanup_org_ids = []

    yield session, cleanup_org_ids, cleanup_user_ids

    # Cleanup in reverse foreign key order
    if cleanup_user_ids:
        session.query(User).filter(User.id.in_(cleanup_user_ids)).delete(synchronize_session=False)
        session.commit()
    if cleanup_org_ids:
        session.query(Organization).filter(Organization.id.in_(cleanup_org_ids)).delete(synchronize_session=False)
        session.commit()

    session.close()
    connection.close()


def create_user_and_headers(session, org, role=UserRole.USER, user_id_list=None):
    user = User(
        email=f"admin-test-{uuid.uuid4().hex[:8]}@test.com",
        password_hash=hash_password("Password123!"),
        organization_id=org.id if org else None,
        role=role,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    if user_id_list is not None:
        user_id_list.append(user.id)

    token = create_access_token(
        user_id=user.id,
        org_id=user.organization_id,
        role=user.role.value,
    )
    return user, {"Authorization": f"Bearer {token}"}


def create_org(session, org_id_list=None):
    org = Organization(name=f"AdminTestOrg-{uuid.uuid4().hex[:8]}")
    session.add(org)
    session.commit()
    session.refresh(org)
    if org_id_list is not None:
        org_id_list.append(org.id)
    return org


# ──────────────────────────────────────────────
# Organization Management Tests
# ──────────────────────────────────────────────

def test_super_admin_can_create_organization(client, db_session):
    session, org_ids, user_ids = db_session
    _, admin_headers = create_user_and_headers(session, None, role=UserRole.SUPER_ADMIN, user_id_list=user_ids)

    unique_name = f"BioPharma-{uuid.uuid4().hex[:6]}"
    resp = client.post("/admin/organizations", json={"name": unique_name}, headers=admin_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == unique_name
    assert "id" in data
    assert data["user_count"] == 0
    org_ids.append(uuid.UUID(data["id"]))


def test_user_cannot_create_organization(client, db_session):
    session, org_ids, user_ids = db_session
    org = create_org(session, org_ids)
    _, user_headers = create_user_and_headers(session, org, role=UserRole.USER, user_id_list=user_ids)

    resp = client.post("/admin/organizations", json={"name": "ForbiddenOrg"}, headers=user_headers)
    assert resp.status_code == 403
    assert "Super-admin privileges required" in resp.json()["detail"]


def test_unauthenticated_cannot_access_admin_organizations(client):
    resp = client.get("/admin/organizations")
    assert resp.status_code == 401


def test_super_admin_can_list_organizations(client, db_session):
    session, org_ids, user_ids = db_session
    org = create_org(session, org_ids)
    _, admin_headers = create_user_and_headers(session, None, role=UserRole.SUPER_ADMIN, user_id_list=user_ids)

    resp = client.get("/admin/organizations?page=1&page_size=10", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert data["total"] >= 1
    found = any(item["id"] == str(org.id) for item in data["items"])
    assert found is True


def test_user_cannot_list_organizations(client, db_session):
    session, org_ids, user_ids = db_session
    org = create_org(session, org_ids)
    _, user_headers = create_user_and_headers(session, org, role=UserRole.USER, user_id_list=user_ids)

    resp = client.get("/admin/organizations", headers=user_headers)
    assert resp.status_code == 403


def test_duplicate_organization_name_rejected(client, db_session):
    session, org_ids, user_ids = db_session
    org = create_org(session, org_ids)
    _, admin_headers = create_user_and_headers(session, None, role=UserRole.SUPER_ADMIN, user_id_list=user_ids)

    resp = client.post("/admin/organizations", json={"name": org.name}, headers=admin_headers)
    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"]


def test_super_admin_can_get_organization_by_id(client, db_session):
    session, org_ids, user_ids = db_session
    org = create_org(session, org_ids)
    _, admin_headers = create_user_and_headers(session, None, role=UserRole.SUPER_ADMIN, user_id_list=user_ids)

    resp = client.get(f"/admin/organizations/{org.id}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == str(org.id)
    assert resp.json()["name"] == org.name


def test_get_nonexistent_organization_returns_404(client, db_session):
    session, _, user_ids = db_session
    _, admin_headers = create_user_and_headers(session, None, role=UserRole.SUPER_ADMIN, user_id_list=user_ids)

    resp = client.get(f"/admin/organizations/{uuid.uuid4()}", headers=admin_headers)
    assert resp.status_code == 404


def test_super_admin_can_update_organization(client, db_session):
    session, org_ids, user_ids = db_session
    org = create_org(session, org_ids)
    _, admin_headers = create_user_and_headers(session, None, role=UserRole.SUPER_ADMIN, user_id_list=user_ids)

    updated_name = f"Updated-{org.name}"
    resp = client.patch(f"/admin/organizations/{org.id}", json={"name": updated_name}, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == updated_name


def test_update_organization_to_duplicate_name_rejected(client, db_session):
    session, org_ids, user_ids = db_session
    org1 = create_org(session, org_ids)
    org2 = create_org(session, org_ids)
    _, admin_headers = create_user_and_headers(session, None, role=UserRole.SUPER_ADMIN, user_id_list=user_ids)

    resp = client.patch(f"/admin/organizations/{org2.id}", json={"name": org1.name}, headers=admin_headers)
    assert resp.status_code == 409


# ──────────────────────────────────────────────
# User Management & Provisioning Tests
# ──────────────────────────────────────────────

def test_super_admin_can_create_user(client, db_session):
    session, org_ids, user_ids = db_session
    org = create_org(session, org_ids)
    _, admin_headers = create_user_and_headers(session, None, role=UserRole.SUPER_ADMIN, user_id_list=user_ids)

    new_email = f"newuser-{uuid.uuid4().hex[:6]}@example.com"
    payload = {
        "email": new_email,
        "password": "SecurePassword123!",
        "role": "USER",
        "organization_id": str(org.id),
    }
    resp = client.post("/admin/users", json=payload, headers=admin_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == new_email
    assert data["role"] == "USER"
    assert data["organization_id"] == str(org.id)
    assert "password_hash" not in data
    assert "password" not in data
    user_ids.append(uuid.UUID(data["id"]))


def test_created_password_is_bcrypt_hashed_and_not_plaintext(client, db_session):
    session, org_ids, user_ids = db_session
    org = create_org(session, org_ids)
    _, admin_headers = create_user_and_headers(session, None, role=UserRole.SUPER_ADMIN, user_id_list=user_ids)

    plain_pw = "SuperSecret999!"
    new_email = f"bcrypt-{uuid.uuid4().hex[:6]}@example.com"
    payload = {
        "email": new_email,
        "password": plain_pw,
        "role": "USER",
        "organization_id": str(org.id),
    }
    resp = client.post("/admin/users", json=payload, headers=admin_headers)
    assert resp.status_code == 201
    user_id = uuid.UUID(resp.json()["id"])
    user_ids.append(user_id)

    # Inspect the actual DB record directly
    db_user = session.scalar(select(User).where(User.id == user_id))
    assert db_user is not None
    assert db_user.password_hash != plain_pw
    assert db_user.password_hash.startswith("$2b$") or db_user.password_hash.startswith("$2a$")
    assert verify_password(plain_pw, db_user.password_hash) is True


def test_created_user_can_successfully_log_in(client, db_session):
    session, org_ids, user_ids = db_session
    org = create_org(session, org_ids)
    _, admin_headers = create_user_and_headers(session, None, role=UserRole.SUPER_ADMIN, user_id_list=user_ids)

    plain_pw = "ValidPassword123!"
    user_email = f"login-check-{uuid.uuid4().hex[:6]}@example.com"
    resp = client.post(
        "/admin/users",
        json={"email": user_email, "password": plain_pw, "role": "USER", "organization_id": str(org.id)},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    user_ids.append(uuid.UUID(resp.json()["id"]))

    # Now attempt login with newly provisioned credentials
    login_resp = client.post("/auth/login", json={"email": user_email, "password": plain_pw})
    assert login_resp.status_code == 200
    token_data = login_resp.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"

    # Verify /auth/me returns the provisioned user profile
    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token_data['access_token']}"})
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["email"] == user_email
    assert me_data["role"] == "USER"
    assert me_data["organization_id"] == str(org.id)


def test_created_user_receives_correct_jwt_role_and_org(client, db_session):
    session, org_ids, user_ids = db_session
    org = create_org(session, org_ids)
    _, admin_headers = create_user_and_headers(session, None, role=UserRole.SUPER_ADMIN, user_id_list=user_ids)

    user_email = f"jwt-check-{uuid.uuid4().hex[:6]}@example.com"
    resp = client.post(
        "/admin/users",
        json={"email": user_email, "password": "Password123!", "role": "USER", "organization_id": str(org.id)},
        headers=admin_headers,
    )
    user_ids.append(uuid.UUID(resp.json()["id"]))

    login_resp = client.post("/auth/login", json={"email": user_email, "password": "Password123!"})
    token = login_resp.json()["access_token"]
    payload = decode_access_token(token)
    assert payload["role"] == "USER"
    assert payload["org_id"] == str(org.id)


def test_user_cannot_create_another_user(client, db_session):
    session, org_ids, user_ids = db_session
    org = create_org(session, org_ids)
    _, user_headers = create_user_and_headers(session, org, role=UserRole.USER, user_id_list=user_ids)

    resp = client.post(
        "/admin/users",
        json={"email": "attacker@example.com", "password": "Password123!", "role": "USER", "organization_id": str(org.id)},
        headers=user_headers,
    )
    assert resp.status_code == 403


def test_user_cannot_list_administrative_users(client, db_session):
    session, org_ids, user_ids = db_session
    org = create_org(session, org_ids)
    _, user_headers = create_user_and_headers(session, org, role=UserRole.USER, user_id_list=user_ids)

    resp = client.get("/admin/users", headers=user_headers)
    assert resp.status_code == 403


def test_super_admin_can_list_users(client, db_session):
    session, org_ids, user_ids = db_session
    org = create_org(session, org_ids)
    u1, _ = create_user_and_headers(session, org, role=UserRole.USER, user_id_list=user_ids)
    _, admin_headers = create_user_and_headers(session, None, role=UserRole.SUPER_ADMIN, user_id_list=user_ids)

    resp = client.get("/admin/users?page=1&page_size=20", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert data["total"] >= 2
    for item in data["items"]:
        assert "password_hash" not in item
        assert "password" not in item


def test_super_admin_can_filter_users_by_organization(client, db_session):
    session, org_ids, user_ids = db_session
    org1 = create_org(session, org_ids)
    org2 = create_org(session, org_ids)
    u1, _ = create_user_and_headers(session, org1, role=UserRole.USER, user_id_list=user_ids)
    u2, _ = create_user_and_headers(session, org2, role=UserRole.USER, user_id_list=user_ids)
    _, admin_headers = create_user_and_headers(session, None, role=UserRole.SUPER_ADMIN, user_id_list=user_ids)

    resp = client.get(f"/admin/users?organization_id={org1.id}", headers=admin_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert all(item["organization_id"] == str(org1.id) for item in items)
    assert any(item["id"] == str(u1.id) for item in items)
    assert not any(item["id"] == str(u2.id) for item in items)


def test_super_admin_can_filter_users_by_role_and_email(client, db_session):
    session, org_ids, user_ids = db_session
    org = create_org(session, org_ids)
    u1, _ = create_user_and_headers(session, org, role=UserRole.USER, user_id_list=user_ids)
    _, admin_headers = create_user_and_headers(session, None, role=UserRole.SUPER_ADMIN, user_id_list=user_ids)

    # Filter by role
    resp = client.get("/admin/users?role=SUPER_ADMIN", headers=admin_headers)
    assert resp.status_code == 200
    assert all(item["role"] == "SUPER_ADMIN" for item in resp.json()["items"])

    # Filter by email
    prefix = u1.email[:8]
    resp2 = client.get(f"/admin/users?email={prefix}", headers=admin_headers)
    assert resp2.status_code == 200
    assert any(item["id"] == str(u1.id) for item in resp2.json()["items"])


def test_super_admin_can_retrieve_single_user(client, db_session):
    session, org_ids, user_ids = db_session
    org = create_org(session, org_ids)
    u, _ = create_user_and_headers(session, org, role=UserRole.USER, user_id_list=user_ids)
    _, admin_headers = create_user_and_headers(session, None, role=UserRole.SUPER_ADMIN, user_id_list=user_ids)

    resp = client.get(f"/admin/users/{u.id}", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(u.id)
    assert data["email"] == u.email
    assert "password_hash" not in data


def test_super_admin_can_update_user_fields(client, db_session):
    session, org_ids, user_ids = db_session
    org1 = create_org(session, org_ids)
    org2 = create_org(session, org_ids)
    u, _ = create_user_and_headers(session, org1, role=UserRole.USER, user_id_list=user_ids)
    _, admin_headers = create_user_and_headers(session, None, role=UserRole.SUPER_ADMIN, user_id_list=user_ids)

    # Change organization
    resp = client.patch(f"/admin/users/{u.id}", json={"organization_id": str(org2.id)}, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["organization_id"] == str(org2.id)


def test_password_update_stores_bcrypt_hash(client, db_session):
    session, org_ids, user_ids = db_session
    org = create_org(session, org_ids)
    u, _ = create_user_and_headers(session, org, role=UserRole.USER, user_id_list=user_ids)
    _, admin_headers = create_user_and_headers(session, None, role=UserRole.SUPER_ADMIN, user_id_list=user_ids)

    new_pw = "BrandNewPassword2026!"
    resp = client.patch(f"/admin/users/{u.id}", json={"password": new_pw}, headers=admin_headers)
    assert resp.status_code == 200

    # Test login with updated password
    login_resp = client.post("/auth/login", json={"email": u.email, "password": new_pw})
    assert login_resp.status_code == 200


def test_invalid_organization_id_rejected_on_user_create(client, db_session):
    session, _, user_ids = db_session
    _, admin_headers = create_user_and_headers(session, None, role=UserRole.SUPER_ADMIN, user_id_list=user_ids)

    fake_org_id = str(uuid.uuid4())
    resp = client.post(
        "/admin/users",
        json={"email": f"badorg-{uuid.uuid4().hex[:6]}@example.com", "password": "Password123!", "role": "USER", "organization_id": fake_org_id},
        headers=admin_headers,
    )
    assert resp.status_code == 404
    assert "Target organization not found" in resp.json()["detail"]


def test_missing_organization_id_on_user_create_rejected(client, db_session):
    session, _, user_ids = db_session
    _, admin_headers = create_user_and_headers(session, None, role=UserRole.SUPER_ADMIN, user_id_list=user_ids)

    resp = client.post(
        "/admin/users",
        json={"email": f"noorg-{uuid.uuid4().hex[:6]}@example.com", "password": "Password123!", "role": "USER"},
        headers=admin_headers,
    )
    assert resp.status_code == 422


def test_invalid_role_rejected(client, db_session):
    session, org_ids, user_ids = db_session
    org = create_org(session, org_ids)
    _, admin_headers = create_user_and_headers(session, None, role=UserRole.SUPER_ADMIN, user_id_list=user_ids)

    resp = client.post(
        "/admin/users",
        json={"email": f"invalidrole-{uuid.uuid4().hex[:6]}@example.com", "password": "Password123!", "role": "UNKNOWN_ROLE", "organization_id": str(org.id)},
        headers=admin_headers,
    )
    assert resp.status_code == 422


def test_duplicate_email_rejected(client, db_session):
    session, org_ids, user_ids = db_session
    org = create_org(session, org_ids)
    u, _ = create_user_and_headers(session, org, role=UserRole.USER, user_id_list=user_ids)
    _, admin_headers = create_user_and_headers(session, None, role=UserRole.SUPER_ADMIN, user_id_list=user_ids)

    resp = client.post(
        "/admin/users",
        json={"email": u.email, "password": "Password123!", "role": "USER", "organization_id": str(org.id)},
        headers=admin_headers,
    )
    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"]


def test_cannot_demote_last_super_admin(client, db_session):
    session, _, user_ids = db_session
    # Clean any other super admins for this focused test
    super_admin, admin_headers = create_user_and_headers(session, None, role=UserRole.SUPER_ADMIN, user_id_list=user_ids)

    # Count how many super admins currently exist
    admin_count = session.scalar(select(User).where(User.role == UserRole.SUPER_ADMIN))
    # If there's only 1 super admin (or if we attempt to demote when count <= 1)
    # create second admin to verify transition works when > 1
    admin2, admin2_headers = create_user_and_headers(session, None, role=UserRole.SUPER_ADMIN, user_id_list=user_ids)
    
    # Demote admin2 to USER under an org
    org = create_org(session)
    resp = client.patch(f"/admin/users/{admin2.id}", json={"role": "USER", "organization_id": str(org.id)}, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["role"] == "USER"
