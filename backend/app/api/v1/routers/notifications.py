"""In-app notifications and delivery preferences."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_session, page_params, require
from app.core.config import settings
from app.core.enums import NotificationEvent
from app.core.exceptions import NotFoundError
from app.models.system import Notification, NotificationPreference
from app.schemas.common import Message, Page, PageParams

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", dependencies=[Depends(require("notification:read"))])
def list_notifications(
    user=Depends(current_user),
    db: Session = Depends(db_session),
    params: PageParams = Depends(page_params),
    unread_only: bool = False,
) -> Page:
    stmt = select(Notification).where(
        (Notification.user_id == user.id) | (Notification.user_id.is_(None))
    )
    count_stmt = select(func.count()).select_from(Notification).where(
        (Notification.user_id == user.id) | (Notification.user_id.is_(None))
    )
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
        count_stmt = count_stmt.where(Notification.is_read.is_(False))

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(Notification.created_at.desc())
        .offset(params.offset)
        .limit(params.page_size)
    ).all()
    return Page(
        items=[
            {
                "id": str(n.id),
                "event": n.event,
                "title": n.title,
                "body": n.body,
                "severity": n.severity,
                "payload": n.payload,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat(),
            }
            for n in rows
        ],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post("/{notification_id}/read", dependencies=[Depends(require("notification:read"))])
def mark_read(
    notification_id: uuid.UUID,
    user=Depends(current_user),
    db: Session = Depends(db_session),
) -> Message:
    notification = db.get(Notification, notification_id)
    if notification is None:
        raise NotFoundError("Notification not found.")
    notification.is_read = True
    db.commit()
    return Message(message="Marked as read.")


@router.post("/read-all", dependencies=[Depends(require("notification:read"))])
def mark_all_read(user=Depends(current_user), db: Session = Depends(db_session)) -> dict:
    rows = db.scalars(
        select(Notification).where(
            Notification.user_id == user.id, Notification.is_read.is_(False)
        )
    ).all()
    for n in rows:
        n.is_read = True
    db.commit()
    return {"marked": len(rows)}


class PreferenceIn(BaseModel):
    event: NotificationEvent
    in_app: bool = True
    telegram: bool = False
    email: bool = False


@router.get("/preferences", dependencies=[Depends(require("notification:read"))])
def preferences(user=Depends(current_user), db: Session = Depends(db_session)) -> dict:
    rows = db.scalars(
        select(NotificationPreference).where(NotificationPreference.user_id == user.id)
    ).all()
    existing = {p.event: p for p in rows}
    return {
        "channels": {
            "in_app": {"available": True},
            "telegram": {
                "available": bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID),
                "blocked_reason": (
                    None
                    if settings.TELEGRAM_BOT_TOKEN
                    else "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are not configured."
                ),
            },
            "email": {
                "available": bool(settings.SMTP_HOST),
                "blocked_reason": (
                    None if settings.SMTP_HOST else "SMTP settings are not configured."
                ),
            },
        },
        "preferences": [
            {
                "event": event.value,
                "in_app": existing[event.value].in_app if event.value in existing else True,
                "telegram": (
                    existing[event.value].telegram if event.value in existing else False
                ),
                "email": existing[event.value].email if event.value in existing else False,
            }
            for event in NotificationEvent
        ],
    }


@router.put("/preferences", dependencies=[Depends(require("notification:write"))])
def set_preference(
    payload: PreferenceIn,
    user=Depends(current_user),
    db: Session = Depends(db_session),
) -> Message:
    pref = db.scalar(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user.id,
            NotificationPreference.event == payload.event.value,
        )
    )
    if pref is None:
        pref = NotificationPreference(user_id=user.id, event=payload.event.value)
        db.add(pref)
    pref.in_app = payload.in_app
    pref.telegram = payload.telegram
    pref.email = payload.email
    db.commit()
    return Message(message="Notification preference saved.")
