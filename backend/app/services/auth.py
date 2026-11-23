"""Authentication: login, refresh, logout, password changes.

Lockout, session revocation and audit entries live here rather than in the
router, so a future CLI or worker gets the same behaviour.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError
from app.core.logging import get_logger
from app.core.market_calendar import now_ist
from app.core.security import (
    ACCESS,
    REFRESH,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    validate_password_strength,
    verify_password,
)
from app.models.system import Role, User, UserSession
from app.services import audit

log = get_logger(__name__)

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def get_user_by_identifier(db: Session, identifier: str) -> User | None:
    return db.scalar(
        select(User).where(or_(User.username == identifier, User.email == identifier.lower()))
    )


def authenticate(
    db: Session, identifier: str, password: str, *, ip: str | None = None
) -> tuple[User, str, str]:
    user = get_user_by_identifier(db, identifier)

    # Same error text whether the user exists or not - no account enumeration.
    generic = AuthenticationError("Incorrect username or password.")

    if user is None:
        raise generic

    now = now_ist()
    if user.locked_until and user.locked_until > now:
        raise AuthenticationError(
            f"Account locked until {user.locked_until.isoformat()} after repeated "
            "failed sign-in attempts."
        )

    if not verify_password(password, user.hashed_password):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
            user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
            audit.record(
                db,
                action="auth.account_locked",
                user_id=user.id,
                severity="WARNING",
                description=f"Locked after {user.failed_login_attempts} failed attempts.",
                ip_address=ip,
            )
        audit.record(
            db, action="auth.login_failed", user_id=user.id, severity="WARNING", ip_address=ip
        )
        db.commit()
        raise generic

    if not user.is_active:
        raise AuthenticationError("This account is disabled.")

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now

    access = create_access_token(
        str(user.id),
        extra={"username": user.username, "roles": [r.name for r in user.roles]},
    )
    refresh = create_refresh_token(str(user.id))
    payload = decode_token(refresh, expected_type=REFRESH)

    db.add(
        UserSession(
            user_id=user.id,
            refresh_token_jti=payload["jti"],
            ip_address=ip,
            expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    audit.record(db, action="auth.login", user_id=user.id, ip_address=ip)
    db.commit()
    log.info("login_success", user_id=str(user.id), username=user.username)
    return user, access, refresh


def refresh_tokens(db: Session, refresh_token: str) -> tuple[str, str]:
    payload = decode_token(refresh_token, expected_type=REFRESH)
    jti = payload["jti"]

    session = db.scalar(select(UserSession).where(UserSession.refresh_token_jti == jti))
    if session is None or not session.is_active:
        raise AuthenticationError("Refresh token is no longer valid.")
    if session.expires_at <= now_ist():
        session.is_active = False
        db.commit()
        raise AuthenticationError("Refresh token has expired.")

    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Account is unavailable.")

    # Rotate: the presented refresh token is retired as it is exchanged.
    session.is_active = False
    session.revoked_at = now_ist()

    access = create_access_token(
        str(user.id),
        extra={"username": user.username, "roles": [r.name for r in user.roles]},
    )
    new_refresh = create_refresh_token(str(user.id))
    new_payload = decode_token(new_refresh, expected_type=REFRESH)
    db.add(
        UserSession(
            user_id=user.id,
            refresh_token_jti=new_payload["jti"],
            ip_address=session.ip_address,
            expires_at=now_ist() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    db.commit()
    return access, new_refresh


def logout(db: Session, user_id: uuid.UUID, refresh_token: str | None = None) -> None:
    q = select(UserSession).where(
        UserSession.user_id == user_id, UserSession.is_active.is_(True)
    )
    if refresh_token:
        try:
            jti = decode_token(refresh_token, expected_type=REFRESH)["jti"]
            q = q.where(UserSession.refresh_token_jti == jti)
        except AuthenticationError:
            pass  # expired/invalid token still ends every session below

    for session in db.scalars(q).all():
        session.is_active = False
        session.revoked_at = now_ist()
    audit.record(db, action="auth.logout", user_id=user_id)
    db.commit()


def resolve_access_token(db: Session, token: str) -> User:
    payload = decode_token(token, expected_type=ACCESS)
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise AuthenticationError("Malformed token subject.") from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Account is unavailable.")
    return user


def create_user(
    db: Session,
    *,
    email: str,
    username: str,
    password: str,
    full_name: str | None = None,
    role_names: list[str] | None = None,
    is_superuser: bool = False,
    actor_id: uuid.UUID | None = None,
) -> User:
    email = email.lower()
    if get_user_by_identifier(db, email) or get_user_by_identifier(db, username):
        raise ConflictError("A user with that email or username already exists.")

    validate_password_strength(password)
    user = User(
        email=email,
        username=username,
        full_name=full_name,
        hashed_password=hash_password(password),
        is_superuser=is_superuser,
    )
    for name in role_names or ["Viewer"]:
        role = db.scalar(select(Role).where(Role.name == name))
        if role is None:
            raise NotFoundError(f"Role '{name}' does not exist.")
        user.roles.append(role)

    db.add(user)
    db.flush()
    audit.record(
        db,
        action="user.create",
        user_id=actor_id,
        entity_type="user",
        entity_id=user.id,
        after={"username": username, "email": email, "roles": role_names},
    )
    db.commit()
    db.refresh(user)
    return user


def change_password(
    db: Session, user: User, current_password: str, new_password: str
) -> None:
    if not verify_password(current_password, user.hashed_password):
        raise AuthenticationError("Current password is incorrect.")
    validate_password_strength(new_password)
    user.hashed_password = hash_password(new_password)

    # Changing a password ends every other session.
    for session in db.scalars(
        select(UserSession).where(
            UserSession.user_id == user.id, UserSession.is_active.is_(True)
        )
    ).all():
        session.is_active = False
        session.revoked_at = now_ist()

    audit.record(db, action="auth.password_changed", user_id=user.id, severity="WARNING")
    db.commit()
