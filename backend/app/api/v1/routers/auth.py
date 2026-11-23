"""Authentication routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import client_ip, current_user, db_session
from app.core.config import settings
from app.schemas.auth import (
    LoginRequest,
    PasswordChange,
    RefreshRequest,
    TokenPair,
    UserOut,
)
from app.schemas.common import Message
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenPair)
def login(payload: LoginRequest, request: Request, db: Session = Depends(db_session)) -> TokenPair:
    _, access, refresh = auth_service.authenticate(
        db, payload.username, payload.password, ip=client_ip(request)
    )
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, db: Session = Depends(db_session)) -> TokenPair:
    access, new_refresh = auth_service.refresh_tokens(db, payload.refresh_token)
    return TokenPair(
        access_token=access,
        refresh_token=new_refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", response_model=Message)
def logout(
    payload: RefreshRequest | None = None,
    user=Depends(current_user),
    db: Session = Depends(db_session),
) -> Message:
    auth_service.logout(db, user.id, payload.refresh_token if payload else None)
    return Message(message="Signed out.")


@router.get("/me", response_model=UserOut)
def me(user=Depends(current_user)) -> UserOut:
    return UserOut.model_validate(user)


@router.get("/me/permissions", response_model=list[str])
def my_permissions(user=Depends(current_user)) -> list[str]:
    from app.core.permissions import ALL_CODES

    return sorted(ALL_CODES) if user.is_superuser else sorted(user.permission_codes)


@router.post("/change-password", response_model=Message)
def change_password(
    payload: PasswordChange,
    user=Depends(current_user),
    db: Session = Depends(db_session),
) -> Message:
    auth_service.change_password(db, user, payload.current_password, payload.new_password)
    return Message(message="Password changed. Other sessions have been signed out.")
