from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    username: str = Field(..., description="Username or email")
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class PermissionOut(ORMModel):
    id: uuid.UUID
    code: str
    resource: str
    action: str
    is_sensitive: bool


class RoleOut(ORMModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    is_system: bool
    permissions: list[PermissionOut] = []


class UserOut(ORMModel):
    id: uuid.UUID
    email: str
    username: str
    full_name: str | None = None
    is_active: bool
    is_superuser: bool
    last_login_at: datetime | None = None
    roles: list[RoleOut] = []


class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    full_name: str | None = None
    password: str
    role_names: list[str] = Field(default_factory=lambda: ["Viewer"])


class UserUpdate(BaseModel):
    full_name: str | None = None
    is_active: bool | None = None
    role_names: list[str] | None = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str
