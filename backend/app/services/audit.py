"""Audit logging.

Append-only by policy: this module only ever inserts. There is no update or
delete helper, and no API route exposes one.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.market_calendar import now_ist
from app.models.system import AuditLog


def record(
    db: Session,
    *,
    action: str,
    user_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: Any = None,
    description: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    ip_address: str | None = None,
    severity: str = "INFO",
    extra: dict | None = None,
    commit: bool = False,
) -> AuditLog:
    entry = AuditLog(
        created_at=now_ist(),
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        description=description,
        before_state=before,
        after_state=after,
        ip_address=ip_address,
        severity=severity,
        extra=extra or {},
    )
    db.add(entry)
    db.flush()
    if commit:
        db.commit()
    return entry
