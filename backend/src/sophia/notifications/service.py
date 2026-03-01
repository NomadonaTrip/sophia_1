"""Notification scheduling, value signal detection, and preference enforcement.

Key guarantees:
- No email is sent to any client without an explicit NotificationPreference
  record existing with is_active=True.
- Value signals require operator approval before email send.
- Frequency enforcement: weekly=7d, biweekly=14d, monthly=30d since last send.
- Multiple small wins for the same client are consolidated into a single signal.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sophia.notifications.models import (
    NotificationLog,
    NotificationPreference,
    ValueSignal,
)

logger = logging.getLogger(__name__)

# Frequency to days mapping
_FREQUENCY_DAYS = {
    "weekly": 7,
    "biweekly": 14,
    "monthly": 30,
}


def _is_notification_due(
    db: Session,
    client_id: int,
    frequency: str,
) -> bool:
    """Check whether a client's next notification is due.

    Returns True if no notification has ever been sent or if enough days
    have elapsed since the last sent notification for this client.
    """
    days = _FREQUENCY_DAYS.get(frequency)
    if days is None:
        return False  # disabled or unknown frequency

    last_sent = db.execute(
        select(func.max(NotificationLog.sent_at))
        .where(NotificationLog.client_id == client_id)
        .where(NotificationLog.notification_type == "performance_report")
        .where(NotificationLog.status == "sent")
    ).scalar()

    if last_sent is None:
        return True  # never sent before

    return (datetime.now() - last_sent) >= timedelta(days=days)


def _gather_client_metrics(db: Session, client_id: int) -> dict:
    """Gather recent performance metrics for a client from analytics.

    Uses a try/except ImportError so the notification module works even
    if the analytics module is not yet available.
    """
    metrics: dict = {}
    try:
        from sophia.analytics.models import EngagementMetric, KPISnapshot

        # Get the most recent KPI snapshot
        snapshot = db.execute(
            select(KPISnapshot)
            .where(KPISnapshot.client_id == client_id)
            .order_by(KPISnapshot.week_end.desc())
            .limit(1)
        ).scalar_one_or_none()

        if snapshot:
            metrics["engagement_rate"] = snapshot.engagement_rate
            metrics["reach_growth_pct"] = snapshot.reach_growth_pct
            metrics["follower_growth_pct"] = snapshot.follower_growth_pct
            metrics["save_rate"] = snapshot.save_rate
            metrics["share_rate"] = snapshot.share_rate

        # Get recent raw metrics for reach/impressions
        from datetime import date, timedelta as td

        week_ago = date.today() - td(days=7)
        recent_metrics = db.execute(
            select(EngagementMetric)
            .where(EngagementMetric.client_id == client_id)
            .where(EngagementMetric.metric_date >= week_ago)
        ).scalars().all()

        for m in recent_metrics:
            if m.metric_name == "reach":
                metrics["reach"] = metrics.get("reach", 0) + m.metric_value
            elif m.metric_name == "impressions":
                metrics["impressions"] = metrics.get("impressions", 0) + m.metric_value
            elif m.metric_name == "follower_growth":
                metrics["follower_growth"] = metrics.get("follower_growth", 0) + m.metric_value

    except ImportError:
        logger.debug("Analytics module not available, returning empty metrics")

    return metrics


def _get_client_email_and_name(
    db: Session, client_id: int, pref: NotificationPreference
) -> tuple[str, str]:
    """Get the client email from preference and name from client record."""
    email = pref.email_address
    name = "Valued Client"
    try:
        from sophia.intelligence.models import Client

        client = db.get(Client, client_id)
        if client:
            name = client.name
    except ImportError:
        pass
    return email, name


async def process_notification_queue(db: Session) -> dict:
    """Process pending performance report notifications for all active clients.

    Called by APScheduler every 6 hours. Checks each client's frequency
    setting and sends if due.

    CRITICAL: No email is sent without explicit NotificationPreference existing.

    Returns:
        Summary dict with clients_processed, emails_sent, emails_failed.
    """
    from sophia.notifications.email import send_performance_report

    result = {"clients_processed": 0, "emails_sent": 0, "emails_failed": 0}

    # Only process clients with active notification preferences
    prefs = db.execute(
        select(NotificationPreference)
        .where(NotificationPreference.is_active == True)  # noqa: E712
        .where(NotificationPreference.frequency != "disabled")
    ).scalars().all()

    for pref in prefs:
        result["clients_processed"] += 1

        if not _is_notification_due(db, pref.client_id, pref.frequency):
            continue

        email, name = _get_client_email_and_name(db, pref.client_id, pref)
        metrics = _gather_client_metrics(db, pref.client_id)

        # Build period string
        now = datetime.now()
        days = _FREQUENCY_DAYS.get(pref.frequency, 30)
        start = now - timedelta(days=days)
        period = f"{start.strftime('%b %d')} - {now.strftime('%b %d, %Y')}"

        # Gather comparisons (previous period vs current)
        comparisons: dict = {}  # TODO: compute from KPISnapshot history

        # Gather highlights
        highlights: list[str] = []  # TODO: extract from analytics

        subject = f"Your Content Performance Report - {period}"

        try:
            message_id = await send_performance_report(
                client_email=email,
                client_name=name,
                metrics=metrics,
                period=period,
                highlights=highlights,
                comparisons=comparisons,
            )

            log = NotificationLog(
                client_id=pref.client_id,
                notification_type="performance_report",
                subject=subject,
                resend_message_id=message_id,
                status="sent" if message_id else "failed",
                sent_at=datetime.now(),
                error_message=None if message_id else "Send returned None",
            )
            db.add(log)
            db.commit()

            if message_id:
                result["emails_sent"] += 1
            else:
                result["emails_failed"] += 1

        except Exception as e:
            logger.exception("Failed to send report for client %d", pref.client_id)
            log = NotificationLog(
                client_id=pref.client_id,
                notification_type="performance_report",
                subject=subject,
                status="failed",
                sent_at=datetime.now(),
                error_message=str(e),
            )
            db.add(log)
            db.commit()
            result["emails_failed"] += 1

    return result


async def check_threshold_notifications(db: Session) -> dict:
    """Check for posts exceeding engagement thresholds and send targeted notifications.

    For each client with engagement_threshold set, checks recent posts
    against the threshold and sends notification if exceeded.

    Returns:
        Summary dict with checked and sent counts.
    """
    from sophia.notifications.email import send_performance_report

    result = {"checked": 0, "sent": 0}

    prefs = db.execute(
        select(NotificationPreference)
        .where(NotificationPreference.is_active == True)  # noqa: E712
        .where(NotificationPreference.engagement_threshold.isnot(None))
    ).scalars().all()

    for pref in prefs:
        result["checked"] += 1

        try:
            from sophia.analytics.models import EngagementMetric
            from datetime import date, timedelta as td

            # Check recent engagement metrics
            recent = db.execute(
                select(EngagementMetric)
                .where(EngagementMetric.client_id == pref.client_id)
                .where(EngagementMetric.metric_name == "engagement_rate_on_reached")
                .where(EngagementMetric.metric_date >= date.today() - td(days=1))
            ).scalars().all()

            for metric in recent:
                if metric.metric_value >= pref.engagement_threshold:
                    # Check for duplicate notification about this post
                    already_notified = db.execute(
                        select(NotificationLog)
                        .where(NotificationLog.client_id == pref.client_id)
                        .where(NotificationLog.notification_type == "milestone")
                        .where(NotificationLog.subject.contains(
                            str(metric.content_draft_id or "")
                        ))
                    ).scalar_one_or_none()

                    if already_notified:
                        continue

                    email, name = _get_client_email_and_name(
                        db, pref.client_id, pref
                    )
                    message_id = await send_performance_report(
                        client_email=email,
                        client_name=name,
                        metrics={"engagement_rate": metric.metric_value},
                        period=f"High-performing post on {metric.metric_date}",
                    )

                    log = NotificationLog(
                        client_id=pref.client_id,
                        notification_type="milestone",
                        subject=f"High engagement on post {metric.content_draft_id}",
                        resend_message_id=message_id,
                        status="sent" if message_id else "failed",
                        sent_at=datetime.now(),
                    )
                    db.add(log)
                    db.commit()

                    if message_id:
                        result["sent"] += 1

        except ImportError:
            logger.debug("Analytics module not available for threshold check")

    return result


def detect_value_signals(db: Session) -> list[ValueSignal]:
    """Analyze recent analytics data to detect wins worth communicating.

    Detects three signal types:
    - enquiry_driver: Posts that correlated with inbound enquiries
    - engagement_milestone: First time exceeding engagement benchmarks
    - audience_growth: Significant week-over-week follower growth

    Consolidates: if multiple small wins exist for the same client,
    creates a single combined signal rather than multiple emails.

    Returns:
        List of created ValueSignal records (status="pending").
    """
    created_signals: list[ValueSignal] = []

    try:
        from sophia.analytics.models import ConversionEvent, KPISnapshot
        from sophia.intelligence.models import Client
        from datetime import date, timedelta as td

        # Get all active clients
        clients = db.execute(select(Client)).scalars().all()

        for client in clients:
            signals_for_client: list[dict] = []

            # 1. Enquiry drivers: posts with conversion events
            recent_conversions = db.execute(
                select(ConversionEvent)
                .where(ConversionEvent.client_id == client.id)
                .where(ConversionEvent.event_type == "inquiry")
                .where(ConversionEvent.event_date >= date.today() - td(days=7))
            ).scalars().all()

            if recent_conversions:
                count = len(recent_conversions)
                # Check baseline (average weekly inquiries over past month)
                month_ago = date.today() - td(days=30)
                month_count = db.execute(
                    select(func.count(ConversionEvent.id))
                    .where(ConversionEvent.client_id == client.id)
                    .where(ConversionEvent.event_type == "inquiry")
                    .where(ConversionEvent.event_date >= month_ago)
                ).scalar() or 0

                baseline = month_count / 4.0 if month_count > 0 else 0
                if count > baseline * 1.5 and count >= 3:  # 50% above average, min 3
                    signals_for_client.append({
                        "signal_type": "enquiry_driver",
                        "headline": f"Your content drove {count} enquiries this week!",
                        "details": f"This week's content generated {count} enquiries, compared to your average of {baseline:.0f} per week.",
                        "metric_value": float(count),
                        "metric_baseline": baseline,
                    })

            # 2. Engagement milestones
            latest_kpi = db.execute(
                select(KPISnapshot)
                .where(KPISnapshot.client_id == client.id)
                .order_by(KPISnapshot.week_end.desc())
                .limit(2)
            ).scalars().all()

            if len(latest_kpi) >= 2:
                current, previous = latest_kpi[0], latest_kpi[1]
                if (
                    current.engagement_rate is not None
                    and previous.engagement_rate is not None
                    and current.engagement_rate > previous.engagement_rate * 1.3
                    and current.engagement_rate > 0.03
                ):
                    signals_for_client.append({
                        "signal_type": "engagement_milestone",
                        "headline": f"Engagement rate hit {current.engagement_rate * 100:.1f}%!",
                        "details": f"Your engagement rate jumped from {previous.engagement_rate * 100:.1f}% to {current.engagement_rate * 100:.1f}%. Your audience is responding strongly to recent content.",
                        "metric_value": current.engagement_rate,
                        "metric_baseline": previous.engagement_rate,
                    })

            # 3. Audience growth
            if len(latest_kpi) >= 2:
                current, previous = latest_kpi[0], latest_kpi[1]
                if (
                    current.follower_growth_pct is not None
                    and current.follower_growth_pct > 0.10  # >10% growth
                ):
                    signals_for_client.append({
                        "signal_type": "audience_growth",
                        "headline": f"Your audience grew {current.follower_growth_pct * 100:.0f}% this week!",
                        "details": f"Strong content performance is driving consistent audience growth.",
                        "metric_value": current.follower_growth_pct,
                        "metric_baseline": (
                            previous.follower_growth_pct
                            if previous.follower_growth_pct is not None
                            else 0.0
                        ),
                    })

            # Consolidation: if multiple signals, combine into one
            if len(signals_for_client) > 1:
                combined_headline = f"{len(signals_for_client)} wins this week for your business!"
                details_parts = [s["details"] for s in signals_for_client]
                combined_details = " ".join(details_parts)
                best_signal = max(
                    signals_for_client,
                    key=lambda s: (s.get("metric_value") or 0),
                )
                signal = ValueSignal(
                    client_id=client.id,
                    signal_type=best_signal["signal_type"],
                    headline=combined_headline,
                    details=combined_details,
                    metric_value=best_signal.get("metric_value"),
                    metric_baseline=best_signal.get("metric_baseline"),
                    status="pending",
                )
                db.add(signal)
                created_signals.append(signal)
            elif len(signals_for_client) == 1:
                s = signals_for_client[0]
                signal = ValueSignal(
                    client_id=client.id,
                    signal_type=s["signal_type"],
                    headline=s["headline"],
                    details=s["details"],
                    metric_value=s.get("metric_value"),
                    metric_baseline=s.get("metric_baseline"),
                    status="pending",
                )
                db.add(signal)
                created_signals.append(signal)

        if created_signals:
            db.commit()
            logger.info("Detected %d value signals", len(created_signals))

    except ImportError:
        logger.debug("Analytics/Intelligence module not available for value signal detection")

    return created_signals


async def approve_value_signal(
    db: Session,
    signal_id: int,
    review_notes: str | None = None,
) -> ValueSignal | None:
    """Approve a value signal and send the email.

    Flow: pending -> approved -> sent.

    Args:
        db: Database session.
        signal_id: ValueSignal ID.
        review_notes: Optional operator review notes.

    Returns:
        Updated ValueSignal or None if not found or invalid state.
    """
    from sophia.notifications.email import send_value_signal_email

    signal = db.get(ValueSignal, signal_id)
    if signal is None:
        return None

    if signal.status != "pending":
        return None  # can only approve pending signals

    # Mark approved
    signal.status = "approved"
    signal.approved_at = datetime.now()
    db.flush()

    # Get client email from preferences
    pref = db.execute(
        select(NotificationPreference)
        .where(NotificationPreference.client_id == signal.client_id)
        .where(NotificationPreference.is_active == True)  # noqa: E712
    ).scalar_one_or_none()

    if pref is None:
        logger.warning(
            "Cannot send value signal %d: no active preferences for client %d",
            signal_id,
            signal.client_id,
        )
        return signal  # approved but not sent (no email configured)

    email, name = _get_client_email_and_name(db, signal.client_id, pref)

    message_id = await send_value_signal_email(
        client_email=email,
        client_name=name,
        headline=signal.headline,
        details=signal.details,
        metric_value=signal.metric_value,
        metric_baseline=signal.metric_baseline,
    )

    if message_id:
        signal.status = "sent"
        signal.sent_at = datetime.now()

        log = NotificationLog(
            client_id=signal.client_id,
            notification_type="value_signal",
            subject=signal.headline,
            resend_message_id=message_id,
            status="sent",
            sent_at=datetime.now(),
        )
        db.add(log)
    else:
        # Approved but send failed
        log = NotificationLog(
            client_id=signal.client_id,
            notification_type="value_signal",
            subject=signal.headline,
            status="failed",
            sent_at=datetime.now(),
            error_message="Email send returned None",
        )
        db.add(log)

    db.commit()
    return signal


def dismiss_value_signal(db: Session, signal_id: int) -> ValueSignal | None:
    """Dismiss a value signal (no email sent).

    Args:
        db: Database session.
        signal_id: ValueSignal ID.

    Returns:
        Updated ValueSignal or None if not found or invalid state.
    """
    signal = db.get(ValueSignal, signal_id)
    if signal is None:
        return None

    if signal.status != "pending":
        return None  # can only dismiss pending signals

    signal.status = "dismissed"
    db.commit()
    return signal


def get_notification_history(
    db: Session,
    client_id: int | None = None,
    limit: int = 50,
) -> list[NotificationLog]:
    """Retrieve notification history, optionally filtered by client.

    Args:
        db: Database session.
        client_id: Optional client ID filter.
        limit: Maximum number of records to return.

    Returns:
        List of NotificationLog entries, ordered by sent_at desc.
    """
    query = select(NotificationLog).order_by(NotificationLog.sent_at.desc()).limit(limit)

    if client_id is not None:
        query = query.where(NotificationLog.client_id == client_id)

    return list(db.execute(query).scalars().all())


def schedule_client_notifications(
    db: Session,
    client_id: int,
    frequency: str,
    email_address: str,
    **kwargs,
) -> NotificationPreference:
    """Create or update notification preferences for a client.

    Args:
        db: Database session.
        client_id: Client ID.
        frequency: Notification frequency.
        email_address: Client's email address.
        **kwargs: Additional preference fields.

    Returns:
        Created or updated NotificationPreference.
    """
    existing = db.execute(
        select(NotificationPreference)
        .where(NotificationPreference.client_id == client_id)
    ).scalar_one_or_none()

    if existing:
        existing.frequency = frequency
        existing.email_address = email_address
        for k, v in kwargs.items():
            if hasattr(existing, k) and v is not None:
                setattr(existing, k, v)
        db.commit()
        return existing

    pref = NotificationPreference(
        client_id=client_id,
        frequency=frequency,
        email_address=email_address,
        **{k: v for k, v in kwargs.items() if v is not None},
    )
    db.add(pref)
    db.commit()
    return pref
