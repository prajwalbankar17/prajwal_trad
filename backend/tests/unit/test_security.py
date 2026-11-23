"""Password hashing, strength rules and JWT handling."""

from __future__ import annotations

import time

import pytest

from app.core.exceptions import AuthenticationError, ValidationError
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


def test_hash_is_salted_and_verifiable():
    first = hash_password("Str0ng!Password")
    second = hash_password("Str0ng!Password")
    assert first != second            # distinct salts
    assert verify_password("Str0ng!Password", first)
    assert verify_password("Str0ng!Password", second)


def test_wrong_password_fails():
    assert not verify_password("wrong", hash_password("Str0ng!Password"))


def test_malformed_hash_is_rejected_not_crashed():
    assert not verify_password("anything", "not-a-bcrypt-hash")


def test_overlong_password_is_rejected_not_truncated():
    """bcrypt silently truncates past 72 bytes; two different long passwords
    must not become interchangeable."""
    with pytest.raises(ValidationError):
        hash_password("a" * 100)


@pytest.mark.parametrize(
    "password",
    ["short", "alllowercase123", "NOLOWERCASE123", "NoDigitsOrSymbols"],
)
def test_weak_passwords_are_rejected(password):
    with pytest.raises(ValidationError):
        validate_password_strength(password)


def test_strong_password_is_accepted():
    validate_password_strength("Str0ng!Passphrase")


def test_access_token_round_trip():
    token = create_access_token("user-123", extra={"roles": ["Admin"]})
    payload = decode_token(token, expected_type=ACCESS)
    assert payload["sub"] == "user-123"
    assert payload["roles"] == ["Admin"]
    assert payload["jti"]


def test_token_type_is_enforced():
    refresh = create_refresh_token("user-123")
    with pytest.raises(AuthenticationError, match="Expected a access token"):
        decode_token(refresh, expected_type=ACCESS)


def test_tampered_token_is_rejected():
    token = create_access_token("user-123")
    tampered = token[:-4] + ("aaaa" if not token.endswith("aaaa") else "bbbb")
    with pytest.raises(AuthenticationError):
        decode_token(tampered)


def test_expired_token_is_rejected(monkeypatch):
    from app.core import security

    monkeypatch.setattr(security.settings, "ACCESS_TOKEN_EXPIRE_MINUTES", -1)
    token = create_access_token("user-123")
    with pytest.raises(AuthenticationError, match="expired"):
        decode_token(token, expected_type=ACCESS)


def test_each_token_has_a_unique_jti():
    a = decode_token(create_refresh_token("u"), expected_type=REFRESH)
    time.sleep(0.01)
    b = decode_token(create_refresh_token("u"), expected_type=REFRESH)
    assert a["jti"] != b["jti"]
