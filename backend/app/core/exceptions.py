"""Domain exceptions.

Every exception carries an HTTP status and a stable machine-readable code so
the frontend can branch on `code` instead of parsing English messages.
"""

from __future__ import annotations


class AppError(Exception):
    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "details": self.details}


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class AuthenticationError(AppError):
    status_code = 401
    code = "authentication_failed"


class PermissionDeniedError(AppError):
    status_code = 403
    code = "permission_denied"


class RateLimitError(AppError):
    status_code = 429
    code = "rate_limited"


# --- Trading domain -------------------------------------------------------


class RiskLimitBreached(AppError):
    """A risk rule blocked the action. Not an error condition - a control."""

    status_code = 409
    code = "risk_limit_breached"


class StaleMarketDataError(AppError):
    """Market data is too old to act on. Never silently treated as live."""

    status_code = 409
    code = "stale_market_data"


class LiveExecutionForbidden(AppError):
    """Hard stop. Live order placement is not available in this build."""

    status_code = 403
    code = "live_execution_forbidden"


class BrokerError(AppError):
    status_code = 502
    code = "broker_error"


class FeatureBlockedError(AppError):
    """A feature is implemented but blocked by a missing external dependency
    (broker credentials, API key, paid data subscription)."""

    status_code = 503
    code = "feature_blocked"


class DataQualityError(AppError):
    status_code = 422
    code = "data_quality_error"
