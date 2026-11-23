"""Health, safety status, settings and audit log."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import db_session, page_params, require
from app.core import safety
from app.core.config import settings
from app.core.market_calendar import market_status, now_ist
from app.db.redis_client import ping as redis_ping
from app.models.system import AuditLog, SystemSetting
from app.schemas.common import Page, PageParams

router = APIRouter(tags=["System"])


@router.get("/health", summary="Liveness and dependency health")
def health(db: Session = Depends(db_session)) -> dict:
    db_ok = True
    db_error = None
    try:
        db.execute(select(1))
    except Exception as exc:  # pragma: no cover - depends on infrastructure
        db_ok = False
        db_error = str(exc)

    redis_ok = redis_ping()
    return {
        "status": "ok" if (db_ok and redis_ok) else "degraded",
        "app": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
        "time_ist": now_ist().isoformat(),
        "market_status": market_status(),
        "dependencies": {
            "postgres": {"ok": db_ok, "error": db_error},
            "redis": {"ok": redis_ok},
        },
        "integrations": {
            "broker_credentials_present": settings.broker_configured,
            "ai_enabled": settings.ai_configured,
        },
        "safety": safety.safety_status(),
    }


@router.get("/safety", summary="Execution-safety status")
def safety_status() -> dict:
    """Always shows that live order placement is impossible in this build."""
    return safety.safety_status()


@router.get("/settings", dependencies=[Depends(require("system:monitor"))])
def list_settings(db: Session = Depends(db_session)) -> list[dict]:
    rows = db.scalars(select(SystemSetting).order_by(SystemSetting.category, SystemSetting.key))
    return [
        {
            "key": s.key,
            "category": s.category,
            "description": s.description,
            "value": "***REDACTED***" if s.is_sensitive else s.value,
        }
        for s in rows
    ]


@router.get("/audit-logs", dependencies=[Depends(require("audit:read"))])
def audit_logs(
    db: Session = Depends(db_session),
    params: PageParams = Depends(page_params),
    action: str | None = Query(None),
    entity_type: str | None = Query(None),
    severity: str | None = Query(None),
) -> Page:
    stmt = select(AuditLog)
    count_stmt = select(func.count()).select_from(AuditLog)
    for column, value in (
        (AuditLog.action, action),
        (AuditLog.entity_type, entity_type),
        (AuditLog.severity, severity),
    ):
        if value:
            stmt = stmt.where(column == value)
            count_stmt = count_stmt.where(column == value)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(AuditLog.created_at.desc())
        .offset(params.offset)
        .limit(params.page_size)
    ).all()
    return Page(
        items=[
            {
                "id": str(r.id),
                "created_at": r.created_at,
                "user_id": str(r.user_id) if r.user_id else None,
                "action": r.action,
                "entity_type": r.entity_type,
                "entity_id": r.entity_id,
                "description": r.description,
                "severity": r.severity,
            }
            for r in rows
        ],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )
