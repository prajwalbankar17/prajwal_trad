"""User and role administration."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_session, require
from app.core.exceptions import NotFoundError, ValidationError
from app.core.permissions import PERMISSIONS
from app.models.system import Permission, Role, User
from app.schemas.auth import UserCreate, UserOut, UserUpdate
from app.schemas.common import Message
from app.services import audit
from app.services import auth as auth_service

router = APIRouter(tags=["Users & Roles"])


@router.get("/users", response_model=list[UserOut], dependencies=[Depends(require("user:read"))])
def list_users(db: Session = Depends(db_session)) -> list[User]:
    return list(db.scalars(select(User).order_by(User.username)).all())


@router.post(
    "/users", response_model=UserOut, status_code=201,
    dependencies=[Depends(require("user:write"))],
)
def create_user(
    payload: UserCreate,
    actor=Depends(current_user),
    db: Session = Depends(db_session),
) -> User:
    return auth_service.create_user(
        db,
        email=payload.email,
        username=payload.username,
        password=payload.password,
        full_name=payload.full_name,
        role_names=payload.role_names,
        actor_id=actor.id,
    )


@router.patch(
    "/users/{user_id}", response_model=UserOut, dependencies=[Depends(require("user:write"))]
)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    actor=Depends(current_user),
    db: Session = Depends(db_session),
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found.")

    before = {
        "is_active": user.is_active,
        "full_name": user.full_name,
        "roles": [r.name for r in user.roles],
    }
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.is_active is not None:
        if user.id == actor.id and not payload.is_active:
            raise ValidationError("You cannot disable your own account.")
        user.is_active = payload.is_active
    if payload.role_names is not None:
        roles = []
        for name in payload.role_names:
            role = db.scalar(select(Role).where(Role.name == name))
            if role is None:
                raise NotFoundError(f"Role '{name}' does not exist.")
            roles.append(role)
        user.roles = roles

    audit.record(
        db, action="user.update", user_id=actor.id, entity_type="user",
        entity_id=user.id, before=before, after=payload.model_dump(exclude_none=True),
        severity="WARNING",
    )
    db.commit()
    db.refresh(user)
    return user


@router.get("/roles", dependencies=[Depends(require("role:read"))])
def list_roles(db: Session = Depends(db_session)) -> list[dict]:
    rows = db.scalars(select(Role).order_by(Role.priority.desc())).all()
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "description": r.description,
            "is_system": r.is_system,
            "priority": r.priority,
            "permissions": sorted(p.code for p in r.permissions),
            "user_count": len(r.users),
        }
        for r in rows
    ]


@router.get("/permissions", dependencies=[Depends(require("role:read"))])
def list_permissions(db: Session = Depends(db_session)) -> list[dict]:
    rows = db.scalars(select(Permission).order_by(Permission.resource, Permission.action)).all()
    seeded = {p.code: p for p in PERMISSIONS}
    return [
        {
            "id": str(p.id),
            "code": p.code,
            "resource": p.resource,
            "action": p.action,
            "description": p.description or (
                seeded[p.code].description if p.code in seeded else None
            ),
            "is_sensitive": p.is_sensitive,
        }
        for p in rows
    ]


@router.put("/roles/{role_id}/permissions", dependencies=[Depends(require("role:write"))])
def set_role_permissions(
    role_id: uuid.UUID,
    permission_codes: list[str],
    actor=Depends(current_user),
    db: Session = Depends(db_session),
) -> dict:
    role = db.get(Role, role_id)
    if role is None:
        raise NotFoundError("Role not found.")

    before = sorted(p.code for p in role.permissions)
    permissions = []
    for code in permission_codes:
        permission = db.scalar(select(Permission).where(Permission.code == code))
        if permission is None:
            raise NotFoundError(f"Permission '{code}' does not exist.")
        permissions.append(permission)
    role.permissions = permissions

    audit.record(
        db, action="role.permissions_changed", user_id=actor.id, entity_type="role",
        entity_id=role.id, before={"permissions": before},
        after={"permissions": sorted(permission_codes)}, severity="CRITICAL",
    )
    db.commit()
    return {"role": role.name, "permissions": sorted(permission_codes)}


@router.delete("/users/{user_id}", dependencies=[Depends(require("user:write"))])
def deactivate_user(
    user_id: uuid.UUID, actor=Depends(current_user), db: Session = Depends(db_session)
) -> Message:
    """Deactivates rather than deletes: a user's audit trail must survive."""
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found.")
    if user.id == actor.id:
        raise ValidationError("You cannot deactivate your own account.")

    user.is_active = False
    audit.record(
        db, action="user.deactivate", user_id=actor.id, entity_type="user",
        entity_id=user.id, severity="WARNING",
    )
    db.commit()
    return Message(
        message=f"User '{user.username}' deactivated. Their records and audit trail are kept."
    )
