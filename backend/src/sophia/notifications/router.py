"""Notification REST API router.

Endpoints for notification preference management, history, value signal
lifecycle, and manual report sending. All async to support Resend's
sync SDK via asyncio.to_thread().
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sophia.notifications.models import (
    NotificationLog,
    NotificationPreference,
    ValueSignal,
)
from sophia.notifications.schemas import (
    NotificationHistoryResponse,
    NotificationLogResponse,
    PreferenceCreate,
    PreferenceResponse,
    PreferenceUpdate,
    ValueSignalApproval,
    ValueSignalListResponse,
    ValueSignalResponse,
)

notification_router = APIRouter(prefix="/api/notifications", tags=["notifications"])


# -- DB dependency placeholder ------------------------------------------------


def _get_db():
    """Yield a SQLAlchemy session. Lazy-imports engine to avoid slow NTFS imports at startup."""
    from sophia.db.engine import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -- Preference management (COMM-02) -----------------------------------------


@notification_router.post("/preferences", response_model=PreferenceResponse, status_code=201)
async def create_preferences(body: PreferenceCreate, db: Session = Depends(_get_db)):
    """Create notification preferences for a client."""
    # Check for existing preferences
    existing = db.execute(
        select(NotificationPreference)
        .where(NotificationPreference.client_id == body.client_id)
    ).scalar_one_or_none()

    if existing:
        raise HTTPException(409, f"Preferences already exist for client {body.client_id}")

    pref = NotificationPreference(
        client_id=body.client_id,
        frequency=body.frequency,
        email_address=body.email_address,
        engagement_threshold=body.engagement_threshold,
        include_metrics=body.include_metrics,
        include_comparisons=body.include_comparisons,
    )
    db.add(pref)
    db.commit()
    db.refresh(pref)
    return pref


@notification_router.get("/preferences/{client_id}", response_model=PreferenceResponse)
async def get_preferences(client_id: int, db: Session = Depends(_get_db)):
    """Get notification preferences for a client."""
    pref = db.execute(
        select(NotificationPreference)
        .where(NotificationPreference.client_id == client_id)
    ).scalar_one_or_none()

    if pref is None:
        raise HTTPException(404, f"No preferences found for client {client_id}")

    return pref


@notification_router.put("/preferences/{client_id}", response_model=PreferenceResponse)
async def update_preferences(
    client_id: int, body: PreferenceUpdate, db: Session = Depends(_get_db)
):
    """Update notification preferences for a client."""
    pref = db.execute(
        select(NotificationPreference)
        .where(NotificationPreference.client_id == client_id)
    ).scalar_one_or_none()

    if pref is None:
        raise HTTPException(404, f"No preferences found for client {client_id}")

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(pref, key, value)

    db.commit()
    db.refresh(pref)
    return pref


@notification_router.delete("/preferences/{client_id}", response_model=PreferenceResponse)
async def deactivate_preferences(client_id: int, db: Session = Depends(_get_db)):
    """Deactivate notifications for a client (soft delete: sets is_active=False)."""
    pref = db.execute(
        select(NotificationPreference)
        .where(NotificationPreference.client_id == client_id)
    ).scalar_one_or_none()

    if pref is None:
        raise HTTPException(404, f"No preferences found for client {client_id}")

    pref.is_active = False
    db.commit()
    db.refresh(pref)
    return pref


# -- Notification history (COMM-01) ------------------------------------------


@notification_router.get("/history", response_model=NotificationHistoryResponse)
async def get_notification_history(
    client_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(_get_db),
):
    """Get notification send history with delivery status."""
    from sophia.notifications.service import get_notification_history as get_history

    items = get_history(db, client_id=client_id, limit=limit)
    total = len(items)
    sent_count = sum(1 for i in items if i.status == "sent")
    failed_count = sum(1 for i in items if i.status == "failed")

    return NotificationHistoryResponse(
        items=items,
        total=total,
        sent_count=sent_count,
        failed_count=failed_count,
    )


@notification_router.get("/history/{notification_id}", response_model=NotificationLogResponse)
async def get_notification_detail(notification_id: int, db: Session = Depends(_get_db)):
    """Get a single notification's details."""
    log = db.get(NotificationLog, notification_id)
    if log is None:
        raise HTTPException(404, f"Notification {notification_id} not found")
    return log


# -- Value signals (COMM-03) -------------------------------------------------


@notification_router.get("/value-signals", response_model=ValueSignalListResponse)
async def list_value_signals(
    client_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(_get_db),
):
    """List value signals with optional filters."""
    query = select(ValueSignal).order_by(ValueSignal.created_at.desc())

    if client_id is not None:
        query = query.where(ValueSignal.client_id == client_id)
    if status is not None:
        query = query.where(ValueSignal.status == status)

    items = list(db.execute(query).scalars().all())
    pending_count = sum(1 for i in items if i.status == "pending")
    sent_count = sum(1 for i in items if i.status == "sent")

    return ValueSignalListResponse(
        items=items,
        pending_count=pending_count,
        sent_count=sent_count,
    )


@notification_router.post("/value-signals/detect")
async def trigger_value_signal_detection(db: Session = Depends(_get_db)):
    """Manually trigger value signal detection from analytics data."""
    from sophia.notifications.service import detect_value_signals

    signals = detect_value_signals(db)
    return {
        "detected": len(signals),
        "signals": [
            {"id": s.id, "client_id": s.client_id, "headline": s.headline}
            for s in signals
        ],
    }


@notification_router.post(
    "/value-signals/{signal_id}/approve", response_model=ValueSignalResponse
)
async def approve_signal(
    signal_id: int,
    body: ValueSignalApproval = ValueSignalApproval(),
    db: Session = Depends(_get_db),
):
    """Approve and send a value signal email."""
    from sophia.notifications.service import approve_value_signal

    signal = await approve_value_signal(db, signal_id, body.review_notes)
    if signal is None:
        raise HTTPException(404, "Value signal not found or not in pending state")
    return signal


@notification_router.post(
    "/value-signals/{signal_id}/dismiss", response_model=ValueSignalResponse
)
async def dismiss_signal(signal_id: int, db: Session = Depends(_get_db)):
    """Dismiss a value signal (no email sent)."""
    from sophia.notifications.service import dismiss_value_signal

    signal = dismiss_value_signal(db, signal_id)
    if signal is None:
        raise HTTPException(404, "Value signal not found or not in pending state")
    return signal


# -- Manual send (operator convenience) --------------------------------------


@notification_router.post("/send-report/{client_id}")
async def send_manual_report(client_id: int, db: Session = Depends(_get_db)):
    """Manually trigger a performance report email for a specific client.

    Bypasses frequency schedule but respects preference existence.
    """
    from sophia.notifications.email import send_performance_report
    from sophia.notifications.service import (
        _gather_client_metrics,
        _get_client_email_and_name,
    )
    from datetime import datetime

    pref = db.execute(
        select(NotificationPreference)
        .where(NotificationPreference.client_id == client_id)
        .where(NotificationPreference.is_active == True)  # noqa: E712
    ).scalar_one_or_none()

    if pref is None:
        raise HTTPException(
            404,
            f"No active notification preferences for client {client_id}. "
            "Configure preferences before sending.",
        )

    email, name = _get_client_email_and_name(db, client_id, pref)
    metrics = _gather_client_metrics(db, client_id)
    now = datetime.now()
    period = f"Manual report - {now.strftime('%B %d, %Y')}"

    message_id = await send_performance_report(
        client_email=email,
        client_name=name,
        metrics=metrics,
        period=period,
    )

    log = NotificationLog(
        client_id=client_id,
        notification_type="performance_report",
        subject=f"Your Content Performance Report - {period}",
        resend_message_id=message_id,
        status="sent" if message_id else "failed",
        sent_at=now,
        error_message=None if message_id else "Send returned None",
    )
    db.add(log)
    db.commit()

    return {
        "status": "sent" if message_id else "failed",
        "message_id": message_id,
        "client_id": client_id,
    }
