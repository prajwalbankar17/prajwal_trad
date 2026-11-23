"""Password hashing and JWT issuing/verification."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import settings
from app.core.exceptions import AuthenticationError, ValidationError

# bcrypt is used directly rather than through passlib: passlib 1.7.4 has been
# unmaintained since 2020 and emits a spurious version-detection error against
# bcrypt >= 4.1. One hashing scheme, no abstraction layer needed.
BCRYPT_ROUNDS = 12

ACCESS = "access"
REFRESH = "refresh"


# --- Passwords ------------------------------------------------------------


def hash_password(plain: str) -> str:
    # bcrypt silently truncates beyond 72 bytes; reject instead of truncating,
    # which would make two different long passwords interchangeable.
    encoded = plain.encode("utf-8")
    if len(encoded) > 72:
        raise ValidationError("Password must be at most 72 bytes.")
    return bcrypt.hashpw(encoded, bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8")[:72], hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def validate_password_strength(plain: str) -> None:
    n = settings.PASSWORD_MIN_LENGTH
    if len(plain) < n:
        raise ValidationError(f"Password must be at least {n} characters.")
    checks = (
        any(c.islower() for c in plain),
        any(c.isupper() for c in plain),
        any(c.isdigit() for c in plain),
        any(not c.isalnum() for c in plain),
    )
    if sum(checks) < 3:
        raise ValidationError(
            "Password must contain at least three of: lowercase, uppercase, "
            "digit, special character."
        )


# --- Tokens ---------------------------------------------------------------


def _create_token(subject: str, token_type: str, expires: timedelta, extra: dict | None) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(subject: str, extra: dict | None = None) -> str:
    return _create_token(
        subject, ACCESS, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES), extra
    )


def create_refresh_token(subject: str) -> str:
    return _create_token(subject, REFRESH, timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS), None)


def decode_token(token: str, *, expected_type: str | None = None) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("Invalid token.") from exc

    if expected_type and payload.get("type") != expected_type:
        raise AuthenticationError(f"Expected a {expected_type} token.")
    return payload
