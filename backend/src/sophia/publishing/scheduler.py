"""APScheduler-based publishing queue with SQLAlchemy job store.

Manages job scheduling, cadence enforcement, global pause/resume.
Uses a separate unencrypted SQLite for APScheduler's job store
(APScheduler's SQLAlchemyJobStore creates its own engine, incompatible
with SQLCipher PRAGMA key).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session

from sophia.approval.models import GlobalPublishState, PublishingQueueEntry

logger = logging.getLogger(__name__)


def create_scheduler(
    scheduler_db_url: str = "sqlite:///data/scheduler.db",
) -> AsyncIOScheduler:
    """Create APScheduler with job store.

    Uses SQLAlchemyJobStore for production (separate unencrypted SQLite).
    For tests, pass scheduler_db_url="sqlite://" for in-memory.
    """
    if scheduler_db_url == "sqlite://":
        # In-memory for tests
        jobstores = {"default": MemoryJobStore()}
    else:
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

        jobstores = {"default": SQLAlchemyJobStore(url=scheduler_db_url)}

    return AsyncIOScheduler(jobstores=jobstores)


async def schedule_publish(
    scheduler: AsyncIOScheduler,
    db: Session,
    draft_id: int,
    platform: str,
    publish_at: datetime,
    cadence_rules: Optional[dict] = None,
) -> PublishingQueueEntry:
    """Schedule a publishing job. Enforces cadence rules.

    Cadence rules (optional):
    - min_hours_between: minimum hours between posts for same client+platform
    - max_posts_per_week: maximum posts per week per client+platform

    Returns the created PublishingQueueEntry.
    """
    from sophia.content.models import ContentDraft

    # Look up the draft to get client_id
    draft = db.query(ContentDraft).filter_by(id=draft_id).first()
    if not draft:
        raise ValueError(f"Draft {draft_id} not found")

    client_id = draft.client_id
    adjusted_time = publish_at

    if cadence_rules:
        adjusted_time = _enforce_cadence(
            db, client_id, platform, publish_at, cadence_rules
        )

    # Create PublishingQueueEntry in DB
    entry = PublishingQueueEntry(
        content_draft_id=draft_id,
        client_id=client_id,
        platform=platform,
        scheduled_at=adjusted_time,
        publish_mode="auto",
        status="queued",
        image_url=getattr(draft, "image_url", None),
    )
    db.add(entry)
    db.flush()

    # Add APScheduler job
    from sophia.publishing.executor import execute_publish

    job_id = f"publish_{draft_id}_{platform}"
    scheduler.add_job(
        execute_publish,
        trigger="date",
        run_date=adjusted_time,
        args=[draft_id, platform, None],  # db_session_factory filled at runtime
        id=job_id,
        replace_existing=True,
    )

    logger.info(
        "Scheduled draft %d for %s at %s (job: %s)",
        draft_id, platform, adjusted_time, job_id,
    )

    return entry


def _enforce_cadence(
    db: Session,
    client_id: int,
    platform: str,
    requested_at: datetime,
    cadence_rules: dict,
) -> datetime:
    """Enforce cadence rules, adjusting the publish time if needed.

    Returns the adjusted publish_at datetime.
    """
    adjusted = requested_at

    min_hours = cadence_rules.get("min_hours_between")
    if min_hours:
        # Find the latest scheduled post for this client+platform
        latest = (
            db.query(PublishingQueueEntry)
            .filter_by(client_id=client_id, platform=platform)
            .filter(PublishingQueueEntry.status.in_(("queued", "publishing", "published")))
            .order_by(PublishingQueueEntry.scheduled_at.desc())
            .first()
        )
        if latest and latest.scheduled_at:
            min_gap = timedelta(hours=min_hours)
            earliest_allowed = latest.scheduled_at + min_gap
            if adjusted < earliest_allowed:
                adjusted = earliest_allowed
                logger.info(
                    "Cadence: pushed publish to %s (min %dh gap)",
                    adjusted, min_hours,
                )

    max_per_week = cadence_rules.get("max_posts_per_week")
    if max_per_week:
        # Count posts in the same 7-day window from adjusted time
        week_start = adjusted - timedelta(days=7)
        count = (
            db.query(PublishingQueueEntry)
            .filter_by(client_id=client_id, platform=platform)
            .filter(PublishingQueueEntry.status.in_(("queued", "publishing", "published")))
            .filter(PublishingQueueEntry.scheduled_at >= week_start)
            .filter(PublishingQueueEntry.scheduled_at <= adjusted)
            .count()
        )
        if count >= max_per_week:
            # Push to the next week (7 days from the earliest post in window)
            earliest_in_week = (
                db.query(PublishingQueueEntry)
                .filter_by(client_id=client_id, platform=platform)
                .filter(PublishingQueueEntry.status.in_(("queued", "publishing", "published")))
                .filter(PublishingQueueEntry.scheduled_at >= week_start)
                .order_by(PublishingQueueEntry.scheduled_at.asc())
                .first()
            )
            if earliest_in_week and earliest_in_week.scheduled_at:
                adjusted = earliest_in_week.scheduled_at + timedelta(days=7)
                logger.info(
                    "Cadence: pushed publish to %s (max %d/week exceeded)",
                    adjusted, max_per_week,
                )

    return adjusted


async def cancel_publish(
    scheduler: AsyncIOScheduler, db: Session, draft_id: int, platform: str
) -> None:
    """Cancel a scheduled publish job."""
    job_id = f"publish_{draft_id}_{platform}"
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass  # Job may not exist

    entry = (
        db.query(PublishingQueueEntry)
        .filter_by(content_draft_id=draft_id, platform=platform, status="queued")
        .first()
    )
    if entry:
        entry.status = "failed"
        entry.error_message = "Cancelled by operator"
        db.flush()


async def pause_all(db: Session) -> None:
    """Global pause: set GlobalPublishState.is_paused = True."""
    state = db.query(GlobalPublishState).first()
    if not state:
        state = GlobalPublishState(
            is_paused=True,
            paused_by="operator",
            paused_at=datetime.now(timezone.utc),
            resume_requires_confirmation=True,
        )
        db.add(state)
    else:
        state.is_paused = True
        state.paused_by = "operator"
        state.paused_at = datetime.now(timezone.utc)
    db.flush()

    # Mark all queued entries as paused
    queued_entries = (
        db.query(PublishingQueueEntry)
        .filter_by(status="queued")
        .all()
    )
    for entry in queued_entries:
        entry.status = "paused"
    db.flush()

    logger.info("Publishing globally paused")


async def resume_all(db: Session, scheduler: AsyncIOScheduler) -> None:
    """Global resume: unset pause, reschedule paused jobs."""
    state = db.query(GlobalPublishState).first()
    if state:
        state.is_paused = False
        state.paused_by = None
        state.paused_at = None
        db.flush()

    # Restore paused entries to queued
    paused_entries = (
        db.query(PublishingQueueEntry)
        .filter_by(status="paused")
        .all()
    )
    for entry in paused_entries:
        entry.status = "queued"
        # Re-add APScheduler job if scheduled_at is in the future
        if entry.scheduled_at and entry.scheduled_at > datetime.now(timezone.utc):
            from sophia.publishing.executor import execute_publish

            job_id = f"publish_{entry.content_draft_id}_{entry.platform}"
            scheduler.add_job(
                execute_publish,
                trigger="date",
                run_date=entry.scheduled_at,
                args=[entry.content_draft_id, entry.platform, None],
                id=job_id,
                replace_existing=True,
            )
    db.flush()

    logger.info("Publishing globally resumed")
