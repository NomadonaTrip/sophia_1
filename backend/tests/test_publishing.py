"""TDD tests for the publishing pipeline.

Covers: APScheduler scheduling, MCP executor dispatch, rate limiter,
cadence enforcement, global pause/resume, stale content detection,
notification service dispatch, and event broadcasting.

Tests mock MCP at the _dispatch_mcp level (NotImplementedError integration point).
APScheduler uses MemoryJobStore for tests. DB uses the session-scoped encrypted
SQLite from conftest.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sophia.approval.events import ApprovalEventBus
from sophia.approval.models import GlobalPublishState, PublishingQueueEntry
from sophia.content.models import ContentDraft
from sophia.intelligence.models import Client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_draft(
    db,
    client_id: int,
    *,
    platform: str = "facebook",
    status: str = "approved",
    image_url: str | None = "https://cdn.example.com/img.png",
) -> ContentDraft:
    """Create a minimal ContentDraft for publishing tests."""
    draft = ContentDraft(
        client_id=client_id,
        platform=platform,
        content_type="feed",
        copy="Test post copy for publishing",
        image_prompt="A scenic photo",
        image_ratio="1:1",
        status=status,
        publish_mode="auto",
        image_url=image_url,
    )
    db.add(draft)
    db.flush()
    return draft


def _make_queue_entry(
    db,
    draft: ContentDraft,
    *,
    scheduled_at: datetime | None = None,
    image_url: str | None = "https://cdn.example.com/img.png",
    status: str = "queued",
) -> PublishingQueueEntry:
    """Create a PublishingQueueEntry linked to a draft."""
    entry = PublishingQueueEntry(
        content_draft_id=draft.id,
        client_id=draft.client_id,
        platform=draft.platform,
        scheduled_at=scheduled_at or datetime.now(timezone.utc) + timedelta(minutes=5),
        publish_mode="auto",
        status=status,
        image_url=image_url,
    )
    db.add(entry)
    db.flush()
    return entry


# ---------------------------------------------------------------------------
# Test 1: schedule_publish creates job
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_schedule_publish_creates_job(db_session, sample_client):
    """Scheduling a publish creates an APScheduler job and a PublishingQueueEntry."""
    from sophia.publishing.scheduler import create_scheduler, schedule_publish

    scheduler = create_scheduler(scheduler_db_url="sqlite://")  # in-memory
    scheduler.start()
    try:
        draft = _make_draft(db_session, sample_client.id)
        publish_at = datetime.now(timezone.utc) + timedelta(hours=1)

        entry = await schedule_publish(
            scheduler, db_session, draft.id, "facebook", publish_at
        )

        # Verify queue entry created
        assert entry is not None
        assert entry.content_draft_id == draft.id
        assert entry.platform == "facebook"
        assert entry.status == "queued"

        # Verify APScheduler job exists
        job = scheduler.get_job(f"publish_{draft.id}_facebook")
        assert job is not None
    finally:
        scheduler.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Test 2: execute_publish dispatches to Facebook
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_publish_dispatches_to_facebook(db_session, sample_client):
    """Mocked MCP dispatch for Facebook called with correct args."""
    from sophia.publishing.executor import execute_publish

    draft = _make_draft(db_session, sample_client.id, platform="facebook")
    entry = _make_queue_entry(db_session, draft)

    mock_result = {"post_id": "fb_12345", "url": "https://facebook.com/post/12345"}

    with patch(
        "sophia.publishing.executor._dispatch_mcp", new_callable=AsyncMock
    ) as mock_mcp:
        mock_mcp.return_value = mock_result
        # Pass a factory that returns the existing session
        await execute_publish(draft.id, "facebook", lambda: db_session)

        mock_mcp.assert_called_once()
        call_args = mock_mcp.call_args
        assert call_args[0][0] == "facebook"  # platform


# ---------------------------------------------------------------------------
# Test 3: execute_publish dispatches to Instagram
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_publish_dispatches_to_instagram(db_session, sample_client):
    """Mocked MCP dispatch for Instagram called with correct args."""
    from sophia.publishing.executor import execute_publish

    draft = _make_draft(db_session, sample_client.id, platform="instagram")
    entry = _make_queue_entry(db_session, draft)

    mock_result = {"post_id": "ig_67890", "url": "https://instagram.com/p/67890"}

    with patch(
        "sophia.publishing.executor._dispatch_mcp", new_callable=AsyncMock
    ) as mock_mcp:
        mock_mcp.return_value = mock_result
        await execute_publish(draft.id, "instagram", lambda: db_session)

        mock_mcp.assert_called_once()
        call_args = mock_mcp.call_args
        assert call_args[0][0] == "instagram"


# ---------------------------------------------------------------------------
# Test 4: publish transitions draft to published
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_transitions_draft_to_published(db_session, sample_client):
    """Successful publish updates draft status to 'published' with published_at timestamp."""
    from sophia.publishing.executor import execute_publish

    draft = _make_draft(db_session, sample_client.id)
    entry = _make_queue_entry(db_session, draft)

    mock_result = {"post_id": "fb_999", "url": "https://facebook.com/post/999"}
    with patch(
        "sophia.publishing.executor._dispatch_mcp", new_callable=AsyncMock
    ) as mock_mcp:
        mock_mcp.return_value = mock_result
        await execute_publish(draft.id, "facebook", lambda: db_session)

    # Draft should be published now
    db_session.refresh(draft)
    assert draft.status == "published"
    assert draft.published_at is not None


# ---------------------------------------------------------------------------
# Test 5: publish stores platform_post_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_stores_platform_post_id(db_session, sample_client):
    """Successful publish stores platform_post_id and platform_post_url on queue entry."""
    from sophia.publishing.executor import execute_publish

    draft = _make_draft(db_session, sample_client.id)
    entry = _make_queue_entry(db_session, draft)

    mock_result = {"post_id": "fb_abc", "url": "https://facebook.com/post/abc"}
    with patch(
        "sophia.publishing.executor._dispatch_mcp", new_callable=AsyncMock
    ) as mock_mcp:
        mock_mcp.return_value = mock_result
        await execute_publish(draft.id, "facebook", lambda: db_session)

    db_session.refresh(entry)
    assert entry.platform_post_id == "fb_abc"
    assert entry.platform_post_url == "https://facebook.com/post/abc"
    assert entry.status == "published"


# ---------------------------------------------------------------------------
# Test 6: publish failure retries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_failure_retries(db_session, sample_client):
    """First failure increments retry_count and reschedules with backoff."""
    from sophia.publishing.executor import execute_publish

    draft = _make_draft(db_session, sample_client.id)
    entry = _make_queue_entry(db_session, draft)
    assert entry.retry_count == 0

    with patch(
        "sophia.publishing.executor._dispatch_mcp", new_callable=AsyncMock
    ) as mock_mcp:
        mock_mcp.side_effect = RuntimeError("MCP dispatch failed")
        # Should not raise -- failures are handled internally
        await execute_publish(draft.id, "facebook", lambda: db_session)

    db_session.refresh(entry)
    assert entry.retry_count == 1
    assert entry.status in ("queued", "failed")  # queued if retrying, failed if max


# ---------------------------------------------------------------------------
# Test 7: publish failure after 3 retries marks failed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_failure_after_3_retries_marks_failed(db_session, sample_client):
    """3rd retry failure sets status to 'failed' and publishes alert event."""
    from sophia.publishing.executor import execute_publish

    draft = _make_draft(db_session, sample_client.id)
    entry = _make_queue_entry(db_session, draft)
    entry.retry_count = 2  # Already retried twice
    db_session.flush()

    with patch(
        "sophia.publishing.executor._dispatch_mcp", new_callable=AsyncMock
    ) as mock_mcp:
        mock_mcp.side_effect = RuntimeError("MCP dispatch failed")
        with patch(
            "sophia.publishing.executor.notify_publish_failed", new_callable=AsyncMock
        ) as mock_notify:
            await execute_publish(draft.id, "facebook", lambda: db_session)
            mock_notify.assert_called_once()

    db_session.refresh(entry)
    assert entry.retry_count == 3
    assert entry.status == "failed"


# ---------------------------------------------------------------------------
# Test 8: rate limiter blocks when at limit
# ---------------------------------------------------------------------------


def test_rate_limiter_blocks_when_at_limit():
    """can_publish returns False when rate limit reached."""
    from sophia.publishing.rate_limiter import RateLimiter

    limiter = RateLimiter()
    # Fill up Facebook limit (200 calls/hour)
    now = datetime.now(timezone.utc)
    limiter._calls["facebook"] = [
        now - timedelta(seconds=i) for i in range(200)
    ]

    assert limiter.can_publish("facebook") is False


# ---------------------------------------------------------------------------
# Test 9: rate limiter allows after window
# ---------------------------------------------------------------------------


def test_rate_limiter_allows_after_window():
    """can_publish returns True after rate limit window resets."""
    from sophia.publishing.rate_limiter import RateLimiter

    limiter = RateLimiter()
    # All calls were 2 hours ago -- window has passed
    old_time = datetime.now(timezone.utc) - timedelta(hours=2)
    limiter._calls["facebook"] = [old_time] * 200

    assert limiter.can_publish("facebook") is True


# ---------------------------------------------------------------------------
# Test 10: cadence enforcement min hours
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cadence_enforcement_min_hours(db_session, sample_client):
    """Scheduling respects minimum hours between posts for same client+platform."""
    from sophia.publishing.scheduler import create_scheduler, schedule_publish

    scheduler = create_scheduler(scheduler_db_url="sqlite://")
    scheduler.start()
    try:
        draft1 = _make_draft(db_session, sample_client.id)
        draft2 = _make_draft(db_session, sample_client.id)

        now = datetime.now(timezone.utc)
        first_time = now + timedelta(hours=1)

        # Schedule first post
        entry1 = await schedule_publish(
            scheduler, db_session, draft1.id, "facebook", first_time,
            cadence_rules={"min_hours_between": 4},
        )

        # Schedule second post too close
        requested_time = first_time + timedelta(hours=1)  # Only 1 hour gap
        entry2 = await schedule_publish(
            scheduler, db_session, draft2.id, "facebook", requested_time,
            cadence_rules={"min_hours_between": 4},
        )

        # Second post should be pushed to at least 4 hours after first
        assert entry2.scheduled_at >= entry1.scheduled_at + timedelta(hours=4)
    finally:
        scheduler.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Test 11: cadence enforcement posts per week
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cadence_enforcement_posts_per_week(db_session, sample_client):
    """Scheduling respects max posts per week per client+platform."""
    from sophia.publishing.scheduler import create_scheduler, schedule_publish

    scheduler = create_scheduler(scheduler_db_url="sqlite://")
    scheduler.start()
    try:
        cadence = {"max_posts_per_week": 3}
        now = datetime.now(timezone.utc)

        # Schedule 3 posts (at the limit)
        for i in range(3):
            draft = _make_draft(db_session, sample_client.id)
            await schedule_publish(
                scheduler, db_session, draft.id, "facebook",
                now + timedelta(hours=i * 24),
                cadence_rules=cadence,
            )

        # 4th post should be pushed to next week
        draft4 = _make_draft(db_session, sample_client.id)
        entry4 = await schedule_publish(
            scheduler, db_session, draft4.id, "facebook",
            now + timedelta(hours=72),
            cadence_rules=cadence,
        )

        # The 4th entry should be pushed beyond the current week window
        # Compare naive datetimes since SQLite may strip timezone
        entry4_time = entry4.scheduled_at.replace(tzinfo=None) if entry4.scheduled_at.tzinfo else entry4.scheduled_at
        now_naive = now.replace(tzinfo=None)
        assert entry4_time > now_naive + timedelta(days=6)
    finally:
        scheduler.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Test 12: global pause halts execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_global_pause_halts_execution(db_session, sample_client):
    """Paused state prevents execute_publish from running."""
    from sophia.publishing.executor import execute_publish

    # Set global pause
    pause_state = GlobalPublishState(
        is_paused=True,
        paused_by="operator:cli",
        paused_at=datetime.now(timezone.utc),
    )
    db_session.add(pause_state)
    db_session.flush()

    draft = _make_draft(db_session, sample_client.id)
    entry = _make_queue_entry(db_session, draft)

    with patch(
        "sophia.publishing.executor._dispatch_mcp", new_callable=AsyncMock
    ) as mock_mcp:
        await execute_publish(draft.id, "facebook", lambda: db_session)
        # MCP should NOT be called when paused
        mock_mcp.assert_not_called()

    db_session.refresh(entry)
    assert entry.status == "paused"


# ---------------------------------------------------------------------------
# Test 13: global resume restores execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_global_resume_restores_execution(db_session, sample_client):
    """Resuming re-enables publishing for paused entries."""
    from sophia.publishing.scheduler import create_scheduler, pause_all, resume_all

    scheduler = create_scheduler(scheduler_db_url="sqlite://")
    scheduler.start()
    try:
        # Pause
        await pause_all(db_session)
        state = db_session.query(GlobalPublishState).first()
        assert state is not None
        assert state.is_paused is True

        # Resume
        await resume_all(db_session, scheduler)
        db_session.refresh(state)
        assert state.is_paused is False
    finally:
        scheduler.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Test 14: publish event broadcast
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_event_broadcast(db_session, sample_client):
    """Successful publish broadcasts 'publish_complete' event with URL."""
    from sophia.publishing.executor import execute_publish

    draft = _make_draft(db_session, sample_client.id)
    entry = _make_queue_entry(db_session, draft)

    mock_result = {"post_id": "fb_bcast", "url": "https://facebook.com/post/bcast"}
    with patch(
        "sophia.publishing.executor._dispatch_mcp", new_callable=AsyncMock
    ) as mock_mcp:
        mock_mcp.return_value = mock_result
        with patch(
            "sophia.publishing.executor.notify_publish_complete", new_callable=AsyncMock
        ) as mock_notify:
            await execute_publish(draft.id, "facebook", lambda: db_session)
            mock_notify.assert_called_once()
            # Should include URL
            call_args = mock_notify.call_args
            assert "facebook.com" in call_args[0][1]  # platform_url arg


# ---------------------------------------------------------------------------
# Test 14b: schedule_publish copies image_url from draft
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_schedule_publish_copies_image_url(db_session, sample_client):
    """schedule_publish copies draft.image_url to entry.image_url."""
    from sophia.publishing.scheduler import create_scheduler, schedule_publish

    scheduler = create_scheduler(scheduler_db_url="sqlite://")
    scheduler.start()
    try:
        draft = _make_draft(
            db_session, sample_client.id, image_url="data/uploads/test.png"
        )
        publish_at = datetime.now(timezone.utc) + timedelta(hours=1)

        entry = await schedule_publish(
            scheduler, db_session, draft.id, "facebook", publish_at
        )

        assert entry.image_url == "data/uploads/test.png"
    finally:
        scheduler.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Test 15: image required before publish
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_image_required_before_publish(db_session, sample_client):
    """Publish fails if no image_url on PublishingQueueEntry."""
    from sophia.publishing.executor import execute_publish

    draft = _make_draft(db_session, sample_client.id)
    # Queue entry WITHOUT image_url
    entry = _make_queue_entry(db_session, draft, image_url=None)

    with patch(
        "sophia.publishing.executor._dispatch_mcp", new_callable=AsyncMock
    ) as mock_mcp:
        await execute_publish(draft.id, "facebook", lambda: db_session)
        # MCP should NOT be called without an image
        mock_mcp.assert_not_called()

    db_session.refresh(entry)
    assert entry.status == "failed"
    assert "image" in (entry.error_message or "").lower()


# ---------------------------------------------------------------------------
# Test 16: stale content detection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stale_content_detection(db_session, sample_client):
    """Content in 'in_review' for >4 hours is flagged as stale."""
    from sophia.publishing.stale_monitor import check_stale_content

    # Create a draft that's been in_review for 5 hours
    draft = _make_draft(db_session, sample_client.id, status="in_review")
    # Manually set updated_at to 5 hours ago
    five_hours_ago = datetime.now(timezone.utc) - timedelta(hours=5)
    db_session.execute(
        ContentDraft.__table__.update()
        .where(ContentDraft.id == draft.id)
        .values(updated_at=five_hours_ago)
    )
    db_session.flush()

    stale_drafts = await check_stale_content(lambda: db_session, stale_hours=4)
    assert len(stale_drafts) >= 1
    assert any(d.id == draft.id for d in stale_drafts)


# ---------------------------------------------------------------------------
# Test 17: stale nudge event broadcast
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stale_nudge_event_broadcast(db_session, sample_client):
    """Stale detection publishes 'content_stale' event."""
    from sophia.publishing.stale_monitor import check_stale_content

    draft = _make_draft(db_session, sample_client.id, status="in_review")
    five_hours_ago = datetime.now(timezone.utc) - timedelta(hours=5)
    db_session.execute(
        ContentDraft.__table__.update()
        .where(ContentDraft.id == draft.id)
        .values(updated_at=five_hours_ago)
    )
    db_session.flush()

    with patch(
        "sophia.publishing.stale_monitor.event_bus", new_callable=lambda: type(
            "MockBus", (), {"publish": AsyncMock()}
        )
    ) as mock_bus:
        await check_stale_content(lambda: db_session, stale_hours=4)
        mock_bus.publish.assert_called()
        call_args = mock_bus.publish.call_args
        assert call_args[0][0] == "content_stale"


# ---------------------------------------------------------------------------
# Test 18: notification service dispatches to channels
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notification_service_dispatches_to_channels():
    """NotificationService publishes to event_bus AND calls registered channel callbacks."""
    from sophia.publishing.notifications import NotificationService

    service = NotificationService()

    channel_callback = AsyncMock()
    service.register_channel(channel_callback)

    with patch(
        "sophia.publishing.notifications.event_bus"
    ) as mock_bus:
        mock_bus.publish = AsyncMock()
        await service.notify("test_event", {"key": "value"})

        # Event bus should be called
        mock_bus.publish.assert_called_once_with("test_event", {"key": "value"})
        # Channel callback should also be called
        channel_callback.assert_called_once_with("test_event", {"key": "value"})


# ---------------------------------------------------------------------------
# Test 19: notification channel failure does not break publish
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notification_channel_failure_does_not_break_publish():
    """A failing registered channel does not prevent other channels or publish from succeeding."""
    from sophia.publishing.notifications import NotificationService

    service = NotificationService()

    # First channel fails
    failing_channel = AsyncMock(side_effect=RuntimeError("channel broke"))
    service.register_channel(failing_channel)

    # Second channel works
    working_channel = AsyncMock()
    service.register_channel(working_channel)

    with patch(
        "sophia.publishing.notifications.event_bus"
    ) as mock_bus:
        mock_bus.publish = AsyncMock()

        # Should not raise even though one channel fails
        await service.notify("test_event", {"key": "value"})

        # Event bus still called
        mock_bus.publish.assert_called_once()
        # Working channel still called
        working_channel.assert_called_once_with("test_event", {"key": "value"})
