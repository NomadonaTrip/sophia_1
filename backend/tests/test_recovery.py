"""TDD tests for content recovery protocol.

Covers: Facebook deletion via MCP, Instagram manual fallback,
recovery log creation, audit trail, urgency levels, event broadcasting,
CLI trigger, and interface attribution (web/telegram/cli).

Tests mock MCP at _dispatch_recovery_mcp level.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sophia.approval.models import PublishingQueueEntry, RecoveryLog
from sophia.content.models import ContentDraft


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_published_draft(
    db,
    client_id: int,
    *,
    platform: str = "facebook",
) -> ContentDraft:
    """Create a ContentDraft in 'published' state with a queue entry."""
    draft = ContentDraft(
        client_id=client_id,
        platform=platform,
        content_type="feed",
        copy="Published post that needs recovery",
        image_prompt="A photo",
        image_ratio="1:1",
        status="published",
        publish_mode="auto",
        published_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db.add(draft)
    db.flush()

    entry = PublishingQueueEntry(
        content_draft_id=draft.id,
        client_id=client_id,
        platform=platform,
        scheduled_at=datetime.now(timezone.utc) - timedelta(hours=2),
        publish_mode="auto",
        status="published",
        platform_post_id=f"{platform}_post_123",
        platform_post_url=f"https://{platform}.com/post/123",
        image_url="https://cdn.example.com/img.png",
    )
    db.add(entry)
    db.flush()

    return draft


# ---------------------------------------------------------------------------
# Test 1: Facebook recovery deletes post
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recover_facebook_deletes_post(db_session, sample_client):
    """Facebook recovery calls MCP delete_post tool and transitions to 'recovered'."""
    from sophia.publishing.recovery import recover_content

    draft = _make_published_draft(db_session, sample_client.id, platform="facebook")

    with patch(
        "sophia.publishing.recovery._dispatch_recovery_mcp", new_callable=AsyncMock
    ) as mock_mcp:
        mock_mcp.return_value = True  # Successful deletion

        with patch(
            "sophia.publishing.recovery.notify_recovery_complete", new_callable=AsyncMock
        ):
            log = await recover_content(
                db_session, draft.id, reason="Contains factual error",
                urgency="immediate", triggered_by="operator:web",
            )

        mock_mcp.assert_called_once_with("facebook", f"facebook_post_123")

    db_session.refresh(draft)
    assert draft.status == "recovered"
    assert log.status == "completed"


# ---------------------------------------------------------------------------
# Test 2: Instagram manual fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recover_instagram_manual_fallback(db_session, sample_client):
    """Instagram recovery sets status to 'manual_recovery_needed' (no delete in ig-mcp)."""
    from sophia.publishing.recovery import recover_content

    draft = _make_published_draft(db_session, sample_client.id, platform="instagram")

    with patch(
        "sophia.publishing.recovery.notify_recovery_complete", new_callable=AsyncMock
    ):
        log = await recover_content(
            db_session, draft.id, reason="Wrong client tagged",
            urgency="immediate", triggered_by="operator:web",
        )

    assert log.status == "manual_recovery_needed"
    # Draft still transitions to recovered (archived internally)
    db_session.refresh(draft)
    assert draft.status == "recovered"


# ---------------------------------------------------------------------------
# Test 3: recovery creates log
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recovery_creates_log(db_session, sample_client):
    """Every recovery operation creates a RecoveryLog entry."""
    from sophia.publishing.recovery import recover_content

    draft = _make_published_draft(db_session, sample_client.id)

    with patch(
        "sophia.publishing.recovery._dispatch_recovery_mcp", new_callable=AsyncMock
    ) as mock_mcp:
        mock_mcp.return_value = True
        with patch(
            "sophia.publishing.recovery.notify_recovery_complete", new_callable=AsyncMock
        ):
            log = await recover_content(
                db_session, draft.id, reason="Policy violation",
            )

    assert isinstance(log, RecoveryLog)
    assert log.content_draft_id == draft.id
    assert log.reason == "Policy violation"
    assert log.client_id == sample_client.id


# ---------------------------------------------------------------------------
# Test 4: recovery archives content
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recovery_archives_content(db_session, sample_client):
    """Recovered content stays in DB with 'recovered' status (not deleted)."""
    from sophia.publishing.recovery import recover_content

    draft = _make_published_draft(db_session, sample_client.id)

    with patch(
        "sophia.publishing.recovery._dispatch_recovery_mcp", new_callable=AsyncMock
    ) as mock_mcp:
        mock_mcp.return_value = True
        with patch(
            "sophia.publishing.recovery.notify_recovery_complete", new_callable=AsyncMock
        ):
            await recover_content(db_session, draft.id, reason="Archive test")

    # Draft still in DB, not deleted
    archived = db_session.query(ContentDraft).filter_by(id=draft.id).first()
    assert archived is not None
    assert archived.status == "recovered"


# ---------------------------------------------------------------------------
# Test 5: immediate urgency executes right away
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recovery_immediate_urgency(db_session, sample_client):
    """'immediate' urgency executes deletion right away."""
    from sophia.publishing.recovery import recover_content

    draft = _make_published_draft(db_session, sample_client.id)

    with patch(
        "sophia.publishing.recovery._dispatch_recovery_mcp", new_callable=AsyncMock
    ) as mock_mcp:
        mock_mcp.return_value = True
        with patch(
            "sophia.publishing.recovery.notify_recovery_complete", new_callable=AsyncMock
        ):
            log = await recover_content(
                db_session, draft.id, reason="Urgent fix",
                urgency="immediate",
            )

    assert log.urgency == "immediate"
    assert log.status == "completed"
    mock_mcp.assert_called_once()


# ---------------------------------------------------------------------------
# Test 6: review urgency creates pending log
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recovery_review_urgency(db_session, sample_client):
    """'review' urgency creates log with 'pending' status for operator assessment."""
    from sophia.publishing.recovery import recover_content

    draft = _make_published_draft(db_session, sample_client.id)

    with patch(
        "sophia.publishing.recovery._dispatch_recovery_mcp", new_callable=AsyncMock
    ) as mock_mcp:
        with patch(
            "sophia.publishing.recovery.notify_recovery_complete", new_callable=AsyncMock
        ):
            log = await recover_content(
                db_session, draft.id, reason="Needs review",
                urgency="review",
            )

    assert log.urgency == "review"
    assert log.status == "pending"
    # MCP should NOT be called for review urgency
    mock_mcp.assert_not_called()


# ---------------------------------------------------------------------------
# Test 7: recovery event broadcast
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recovery_event_broadcast(db_session, sample_client):
    """Recovery completion dispatches 'recovery_complete' via notification_service."""
    from sophia.publishing.recovery import recover_content

    draft = _make_published_draft(db_session, sample_client.id)

    with patch(
        "sophia.publishing.recovery._dispatch_recovery_mcp", new_callable=AsyncMock
    ) as mock_mcp:
        mock_mcp.return_value = True
        with patch(
            "sophia.publishing.recovery.notify_recovery_complete", new_callable=AsyncMock
        ) as mock_notify:
            await recover_content(db_session, draft.id, reason="Event test")
            mock_notify.assert_called_once()


# ---------------------------------------------------------------------------
# Test 8: recovery from web
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recovery_from_web(db_session, sample_client):
    """triggered_by='operator:web' recorded correctly."""
    from sophia.publishing.recovery import recover_content

    draft = _make_published_draft(db_session, sample_client.id)

    with patch(
        "sophia.publishing.recovery._dispatch_recovery_mcp", new_callable=AsyncMock
    ) as mock_mcp:
        mock_mcp.return_value = True
        with patch(
            "sophia.publishing.recovery.notify_recovery_complete", new_callable=AsyncMock
        ):
            log = await recover_content(
                db_session, draft.id, reason="Web recovery",
                triggered_by="operator:web",
            )

    assert log.triggered_by == "operator:web"


# ---------------------------------------------------------------------------
# Test 9: recovery from telegram
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recovery_from_telegram(db_session, sample_client):
    """triggered_by='operator:telegram' recorded correctly."""
    from sophia.publishing.recovery import recover_content

    draft = _make_published_draft(db_session, sample_client.id)

    with patch(
        "sophia.publishing.recovery._dispatch_recovery_mcp", new_callable=AsyncMock
    ) as mock_mcp:
        mock_mcp.return_value = True
        with patch(
            "sophia.publishing.recovery.notify_recovery_complete", new_callable=AsyncMock
        ):
            log = await recover_content(
                db_session, draft.id, reason="Telegram recovery",
                triggered_by="operator:telegram",
            )

    assert log.triggered_by == "operator:telegram"


# ---------------------------------------------------------------------------
# Test 10: recovery from CLI
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recovery_from_cli(db_session, sample_client):
    """triggered_by='operator:cli' recorded correctly."""
    from sophia.publishing.recovery import recover_content

    draft = _make_published_draft(db_session, sample_client.id)

    with patch(
        "sophia.publishing.recovery._dispatch_recovery_mcp", new_callable=AsyncMock
    ) as mock_mcp:
        mock_mcp.return_value = True
        with patch(
            "sophia.publishing.recovery.notify_recovery_complete", new_callable=AsyncMock
        ):
            log = await recover_content(
                db_session, draft.id, reason="CLI recovery",
                triggered_by="operator:cli",
            )

    assert log.triggered_by == "operator:cli"


# ---------------------------------------------------------------------------
# Test 11: CLI recovery command
# ---------------------------------------------------------------------------


def test_cli_recovery_command(db_session, sample_client):
    """CLI 'recover N' command triggers recovery."""
    from sophia.approval.cli import handle_recovery_command

    draft = _make_published_draft(db_session, sample_client.id)

    with patch(
        "sophia.approval.cli.recover_content", new_callable=AsyncMock
    ) as mock_recover:
        mock_log = MagicMock()
        mock_log.status = "completed"
        mock_log.id = 1
        mock_recover.return_value = mock_log

        result = handle_recovery_command(
            db_session, draft.id, reason="CLI test", urgency="immediate",
        )

    mock_recover.assert_called_once()
    call_kwargs = mock_recover.call_args
    assert call_kwargs[1].get("triggered_by") == "operator:cli" or \
           (len(call_kwargs[0]) >= 5 and call_kwargs[0][4] == "operator:cli")
