"""FastAPI dependencies: database session, current user, permission checks."""

from __future__ import annotations

from collections.abc import Callable, Iterator

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.db.session import get_db
from app.models.system import User
from app.schemas.common import PageParams
from app.services import auth as auth_service

bearer = HTTPBearer(auto_error=False)


def db_session() -> Iterator[Session]:
    yield from get_db()


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(db_session),
) -> User:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Authentication required.")
    return auth_service.resolve_access_token(db, credentials.credentials)


def require(*permission_codes: str) -> Callable[..., User]:
    """Route guard. A superuser passes everything; everyone else needs every
    code listed."""

    def _guard(user: User = Depends(current_user)) -> User:
        if user.is_superuser:
            return user
        held = user.permission_codes
        missing = [c for c in permission_codes if c not in held]
        if missing:
            raise PermissionDeniedError(
                "You do not have permission to perform this action.",
                details={"missing_permissions": missing},
            )
        return user

    return _guard


def page_params(page: int = 1, page_size: int = 50) -> PageParams:
    return PageParams(page=page, page_size=page_size)


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None
