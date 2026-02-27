"""APScheduler job that checks for stale un-reviewed content.

Stale content = drafts in "in_review" status for longer than
stale_content_hours (default 4). Publishes "content_stale" event
for each stale draft found.

Registered as a periodic APScheduler job (runs every 30 minutes).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from sophia.approval.events import event_bus
from sophia.content.models import ContentDraft

logger = logging.getLogger(__name__)


async def check_stale_content(
    db_session_factory: Callable[[], Session],
    stale_hours: int = 4,
) -> list[ContentDraft]:
    """Check for content in 'in_review' status beyond stale_content_hours threshold.

    Publishes 'content_stale' event for each stale draft found.
    Returns list of stale drafts for testing convenience.
    """
    db = db_session_factory()
    try:
        now = datetime.now(timezone.utc)
        # SQLite may return naive datetimes; use naive comparison for DB query
        cutoff_naive = (now - timedelta(hours=stale_hours)).replace(tzinfo=None)

        stale_drafts = (
            db.query(ContentDraft)
            .filter(ContentDraft.status == "in_review")
            .filter(ContentDraft.updated_at < cutoff_naive)
            .all()
        )

        for draft in stale_drafts:
            # Handle naive datetimes from SQLite
            updated = draft.updated_at
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            hours_stale = (now - updated).total_seconds() / 3600

            await event_bus.publish(
                "content_stale",
                {
                    "draft_id": draft.id,
                    "client_id": draft.client_id,
                    "hours_stale": round(hours_stale, 1),
                },
            )
            logger.info(
                "Stale content: draft %d (%.1f hours in review)",
                draft.id, hours_stale,
            )

        return stale_drafts

    finally:
        # Do NOT close -- caller manages session lifecycle
        pass


def register_stale_monitor(
    scheduler: Any,
    db_session_factory: Callable[[], Session],
    interval_minutes: int = 30,
) -> None:
    """Register the stale content check as a periodic APScheduler job."""
    scheduler.add_job(
        check_stale_content,
        trigger="interval",
        minutes=interval_minutes,
        args=[db_session_factory],
        id="stale_content_monitor",
        replace_existing=True,
    )
    logger.info(
        "Stale content monitor registered (every %d minutes)", interval_minutes,
    )
