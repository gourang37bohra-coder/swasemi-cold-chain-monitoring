"""Super Admin management API router: Organization and User administration."""

import logging
from typing import Annotated, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth_deps import require_super_admin
from app.core.database import get_db
from app.core.security import hash_password
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.schemas.admin_user import (
    AdminUserCreate,
    AdminUserResponse,
    AdminUserUpdate,
    PaginatedAdminUsersResponse,
)
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationResponse,
    OrganizationUpdate,
    PaginatedOrganizationsResponse,
)

logger = logging.getLogger("coldchain.admin")

# Router enforces SUPER_ADMIN authorization on every admin route
router = APIRouter(
    prefix="/admin",
    tags=["Administration"],
    dependencies=[Depends(require_super_admin)],
)


# ──────────────────────────────────────────────
# ORGANIZATION MANAGEMENT
# ──────────────────────────────────────────────

@router.post(
    "/organizations",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create organization (SUPER_ADMIN only)",
)
def create_organization(
    payload: OrganizationCreate,
    db: Session = Depends(get_db),
) -> OrganizationResponse:
    """Create a new tenant organization."""
    name_clean = payload.name.strip()
    existing = db.scalar(select(Organization).where(Organization.name == name_clean))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An organization with this name already exists.",
        )

    org = Organization(name=name_clean)
    db.add(org)
    db.commit()
    db.refresh(org)

    logger.info("Organization created: %s (id=%s)", org.name, org.id)
    return OrganizationResponse(
        id=org.id,
        name=org.name,
        created_at=org.created_at,
        updated_at=org.updated_at,
        user_count=0,
    )


@router.get(
    "/organizations",
    response_model=PaginatedOrganizationsResponse,
    summary="List organizations (SUPER_ADMIN only)",
)
def list_organizations(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
) -> PaginatedOrganizationsResponse:
    """List all organizations with pagination and user counts."""
    total = db.scalar(select(func.count(Organization.id))) or 0
    offset = (page - 1) * page_size

    query = (
        select(Organization, func.count(User.id).label("user_count"))
        .outerjoin(User, User.organization_id == Organization.id)
        .group_by(Organization.id)
        .order_by(Organization.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = db.execute(query).all()

    items = [
        OrganizationResponse(
            id=org.id,
            name=org.name,
            created_at=org.created_at,
            updated_at=org.updated_at,
            user_count=cnt,
        )
        for org, cnt in rows
    ]

    return PaginatedOrganizationsResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get(
    "/organizations/{organization_id}",
    response_model=OrganizationResponse,
    summary="Get organization by ID (SUPER_ADMIN only)",
)
def get_organization(
    organization_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> OrganizationResponse:
    """Retrieve organization details by ID."""
    row = db.execute(
        select(Organization, func.count(User.id).label("user_count"))
        .outerjoin(User, User.organization_id == Organization.id)
        .where(Organization.id == organization_id)
        .group_by(Organization.id)
    ).first()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found.",
        )

    org, cnt = row
    return OrganizationResponse(
        id=org.id,
        name=org.name,
        created_at=org.created_at,
        updated_at=org.updated_at,
        user_count=cnt,
    )


@router.patch(
    "/organizations/{organization_id}",
    response_model=OrganizationResponse,
    summary="Update organization (SUPER_ADMIN only)",
)
def update_organization(
    organization_id: uuid.UUID,
    payload: OrganizationUpdate,
    db: Session = Depends(get_db),
) -> OrganizationResponse:
    """Update organization attributes."""
    org = db.scalar(select(Organization).where(Organization.id == organization_id))
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found.",
        )

    if payload.name is not None:
        name_clean = payload.name.strip()
        if name_clean != org.name:
            existing = db.scalar(select(Organization).where(Organization.name == name_clean))
            if existing is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="An organization with this name already exists.",
                )
            org.name = name_clean

    db.commit()
    db.refresh(org)

    cnt = db.scalar(select(func.count(User.id)).where(User.organization_id == org.id)) or 0
    return OrganizationResponse(
        id=org.id,
        name=org.name,
        created_at=org.created_at,
        updated_at=org.updated_at,
        user_count=cnt,
    )


# ──────────────────────────────────────────────
# USER MANAGEMENT & PROVISIONING
# ──────────────────────────────────────────────

@router.post(
    "/users",
    response_model=AdminUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create user (SUPER_ADMIN only)",
)
def create_user(
    payload: AdminUserCreate,
    db: Session = Depends(get_db),
) -> User:
    """Provision a new user account under an organization (or as SUPER_ADMIN)."""
    # 1. Email uniqueness check
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email address already exists.",
        )

    # 2. Organization requirement validation
    target_org_id = payload.organization_id
    if payload.role == UserRole.USER:
        if target_org_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="organization_id is required for USER accounts.",
            )
        org = db.scalar(select(Organization).where(Organization.id == target_org_id))
        if org is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Target organization not found.",
            )
    else:
        # SUPER_ADMIN accounts are platform-wide; organization_id is null per schema definition
        target_org_id = None

    # 3. Bcrypt password hashing
    hashed_pw = hash_password(payload.password)

    user = User(
        email=payload.email,
        password_hash=hashed_pw,
        role=payload.role,
        organization_id=target_org_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info("User created: %s (role=%s, org=%s)", user.email, user.role.value, user.organization_id)
    return user


@router.get(
    "/users",
    response_model=PaginatedAdminUsersResponse,
    summary="List users (SUPER_ADMIN only)",
)
def list_users(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    organization_id: Optional[uuid.UUID] = Query(None, description="Filter by organization UUID"),
    role: Optional[UserRole] = Query(None, description="Filter by user role"),
    email: Optional[str] = Query(None, description="Filter by email match"),
) -> PaginatedAdminUsersResponse:
    """List users with database-side filtering and pagination."""
    query = select(User)

    if organization_id is not None:
        query = query.where(User.organization_id == organization_id)
    if role is not None:
        query = query.where(User.role == role)
    if email is not None and email.strip():
        query = query.where(User.email.ilike(f"%{email.strip().lower()}%"))

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    offset = (page - 1) * page_size
    items = db.scalars(query.order_by(User.created_at.desc()).offset(offset).limit(page_size)).all()

    return PaginatedAdminUsersResponse(
        items=list(items),
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get(
    "/users/{user_id}",
    response_model=AdminUserResponse,
    summary="Get user by ID (SUPER_ADMIN only)",
)
def get_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> User:
    """Retrieve a single user account by ID."""
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    return user


@router.patch(
    "/users/{user_id}",
    response_model=AdminUserResponse,
    summary="Update user (SUPER_ADMIN only)",
)
def update_user(
    user_id: uuid.UUID,
    payload: AdminUserUpdate,
    db: Session = Depends(get_db),
) -> User:
    """Update user account attributes (role, organization, or password)."""
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    # 1. Password update
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)

    # 2. Role update
    if payload.role is not None:
        # Prevent demoting the last SUPER_ADMIN account
        if user.role == UserRole.SUPER_ADMIN and payload.role != UserRole.SUPER_ADMIN:
            admin_count = db.scalar(
                select(func.count(User.id)).where(User.role == UserRole.SUPER_ADMIN)
            ) or 0
            if admin_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot demote the last remaining SUPER_ADMIN account.",
                )
        user.role = payload.role
        if payload.role == UserRole.SUPER_ADMIN:
            user.organization_id = None

    # 3. Organization update
    if payload.organization_id is not None:
        if user.role == UserRole.SUPER_ADMIN:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="SUPER_ADMIN accounts cannot be assigned to an organization.",
            )
        org = db.scalar(select(Organization).where(Organization.id == payload.organization_id))
        if org is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Target organization not found.",
            )
        user.organization_id = payload.organization_id

    # 4. Invariant check: USER must have an organization
    if user.role == UserRole.USER and user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="USER accounts must be assigned to an organization.",
        )

    db.commit()
    db.refresh(user)
    return user
