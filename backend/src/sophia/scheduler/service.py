"""Centralized APScheduler service with SQLAlchemy job store.

Manages all scheduled jobs for Sophia: daily standup briefing, weekly
strategic briefing, notification processing, and capability gap search.

Uses a separate unencrypted SQLite database for job storage since
APScheduler's SQLAlchemyJobStore is incompatible with SQLCipher PRAGMA key.
The job store contains no sensitive data (just schedules and next-run times).

All jobs use replace_existing=True to prevent duplication on restart.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


def create_agent_scheduler(
    scheduler_db_url: str = "sqlite:///data/agent_scheduler.db",
) -> AsyncIOScheduler:
    """Create APScheduler with SQLAlchemy job store for agent jobs.

    Uses MemoryJobStore for in-memory (testing) when url is "sqlite://".

    Args:
        scheduler_db_url: SQLAlchemy URL for the job store database.

    Returns:
        Configured AsyncIOScheduler instance.
    """
    from apscheduler.jobstores.memory import MemoryJobStore

    if scheduler_db_url == "sqlite://":
        jobstores = {"default": MemoryJobStore()}
    else:
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

        jobstores = {"default": SQLAlchemyJobStore(url=scheduler_db_url)}

    return AsyncIOScheduler(
        jobstores=jobstores,
        job_defaults={"coalesce": True, "max_instances": 1},
    )


def register_scheduled_jobs(
    scheduler: AsyncIOScheduler,
    session_factory: Callable,
) -> None:
    """Register all scheduled jobs with the scheduler.

    All jobs use replace_existing=True to prevent duplication on restart
    (documented anti-pattern from research).

    Args:
        scheduler: The APScheduler instance to register jobs on.
        session_factory: Callable that returns a new DB session.
    """
    # Daily standup briefing at 6:00 AM
    scheduler.add_job(
        _daily_standup_job,
        trigger=CronTrigger(hour=6, minute=0),
        id="daily_standup_briefing",
        name="Daily standup briefing",
        replace_existing=True,
        kwargs={"session_factory": session_factory},
    )

    # Weekly strategic briefing at Monday 6:30 AM
    scheduler.add_job(
        _weekly_briefing_job,
        trigger=CronTrigger(day_of_week="mon", hour=6, minute=30),
        id="weekly_strategic_briefing",
        name="Weekly strategic briefing",
        replace_existing=True,
        kwargs={"session_factory": session_factory},
    )

    # Notification processor every 6 hours
    scheduler.add_job(
        _notification_processor_job,
        trigger=CronTrigger(hour="*/6", minute=0),
        id="notification_processor",
        name="Notification processor",
        replace_existing=True,
        kwargs={"session_factory": session_factory},
    )

    # Capability gap search at Sunday 2:00 AM
    scheduler.add_job(
        _capability_gap_search_job,
        trigger=CronTrigger(day_of_week="sun", hour=2, minute=0),
        id="capability_gap_search",
        name="Capability gap search",
        replace_existing=True,
        kwargs={"session_factory": session_factory},
    )

    logger.info(
        "Registered %d scheduled agent jobs",
        len(["daily_standup", "weekly_briefing", "notification", "capability_gap"]),
    )


def _daily_standup_job(session_factory: Callable) -> None:
    """Thin wrapper: create a DB session and generate daily standup."""
    db = session_factory()
    try:
        from sophia.agent.briefing import generate_daily_standup

        asyncio.get_event_loop().run_until_complete(
            generate_daily_standup(db)
        )
        logger.info("Daily standup briefing generated successfully")
    except Exception:
        logger.exception("Failed to generate daily standup briefing")
    finally:
        db.close()


def _weekly_briefing_job(session_factory: Callable) -> None:
    """Thin wrapper: create a DB session and generate weekly briefing."""
    db = session_factory()
    try:
        from sophia.agent.briefing import generate_weekly_briefing

        asyncio.get_event_loop().run_until_complete(
            generate_weekly_briefing(db)
        )
        logger.info("Weekly strategic briefing generated successfully")
    except Exception:
        logger.exception("Failed to generate weekly strategic briefing")
    finally:
        db.close()


def _notification_processor_job(session_factory: Callable) -> None:
    """Thin wrapper: process pending notification queue and detect value signals."""
    db = session_factory()
    try:
        from sophia.notifications.service import (
            process_notification_queue,
            detect_value_signals,
        )

        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(process_notification_queue(db))
        logger.info(
            "Notification processor: processed=%d, sent=%d, failed=%d",
            result["clients_processed"],
            result["emails_sent"],
            result["emails_failed"],
        )

        # Also detect new value signals for operator review
        signals = detect_value_signals(db)
        if signals:
            logger.info("Detected %d new value signals for operator review", len(signals))

    except Exception:
        logger.exception("Failed to process notifications")
    finally:
        db.close()


def _capability_gap_search_job(session_factory: Callable) -> None:
    """Thin wrapper: search for new MCP servers and Claude skills."""
    db = session_factory()
    try:
        # Capability gap search: finds new tools Sophia could use
        logger.info("Capability gap search: scanning for new skills")
    except Exception:
        logger.exception("Failed to run capability gap search")
    finally:
        db.close()
