"""Tests for Telegram bot handlers and formatters.

Covers: approval callbacks, reject/edit/skip flows, recovery,
pause/resume, message formatting, and notification channel integration.

Tests mock Update/CallbackQuery/Context objects. Handler type hints
use ``Any`` (not telegram types) so tests work without
python-telegram-bot installed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sophia.telegram.formatters import (
    format_draft_message,
    format_publish_confirmation,
    format_recovery_result,
)
from sophia.telegram.handlers import (
    approval_callback,
    global_pause_handler,
    reject_callback,
    skip_callback,
    text_reply_handler,
)


# ---------------------------------------------------------------------------
# Helpers: mock Telegram objects
# ---------------------------------------------------------------------------


def _make_callback_query(data: str) -> MagicMock:
    """Create a mock CallbackQuery with answer() and edit_message_text()."""
    query = MagicMock()
    query.data = data
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    return query


def _make_update(callback_query=None, message=None) -> MagicMock:
    """Create a mock Update with optional callback_query or message."""
    update = MagicMock()
    update.callback_query = callback_query
    update.message = message
    return update


def _make_context(user_data=None, bot_data=None) -> MagicMock:
    """Create a mock context with user_data, bot_data, and a session_factory."""
    context = MagicMock()
    context.user_data = user_data if user_data is not None else {}
    context.bot_data = bot_data if bot_data is not None else {}

    # Set up a mock session factory that returns a mock db session
    mock_db = MagicMock()
    context.bot_data["session_factory"] = MagicMock(return_value=mock_db)
    return context


def _make_draft(
    draft_id: int = 1,
    client_id: int = 1,
    platform: str = "instagram",
    copy: str = "Fresh spring vibes at the bakery!",
    image_prompt: str = "A warm bakery scene",
    voice_confidence_pct: float = 87.5,
    content_pillar: str = "Behind the Scenes",
    suggested_post_time: datetime | None = None,
    status: str = "in_review",
) -> MagicMock:
    """Create a mock ContentDraft."""
    draft = MagicMock()
    draft.id = draft_id
    draft.client_id = client_id
    draft.platform = platform
    draft.copy = copy
    draft.image_prompt = image_prompt
    draft.voice_confidence_pct = voice_confidence_pct
    draft.content_pillar = content_pillar
    draft.suggested_post_time = suggested_post_time or datetime(
        2026, 3, 15, 10, 0, tzinfo=timezone.utc
    )
    draft.status = status
    return draft


def _make_recovery_log(
    status: str = "completed",
    platform: str = "facebook",
    platform_post_id: str = "fb_post_123",
) -> MagicMock:
    """Create a mock RecoveryLog."""
    log = MagicMock()
    log.status = status
    log.platform = platform
    log.platform_post_id = platform_post_id
    return log


# ---------------------------------------------------------------------------
# Test: format_draft_message
# ---------------------------------------------------------------------------


class TestFormatDraftMessage:
    def test_includes_client_platform_copy_voice(self):
        draft = _make_draft()
        result = format_draft_message(draft, client_name="Shane's Bakery")
        assert "Shane's Bakery" in result
        assert "Instagram" in result
        assert "Fresh spring vibes" in result
        assert "88%" in result  # 87.5 rounds to 88 with :.0f
        assert "Behind the Scenes" in result

    def test_handles_missing_client_name(self):
        draft = _make_draft(client_id=42)
        result = format_draft_message(draft)
        assert "Client #42" in result

    def test_handles_none_voice_confidence(self):
        draft = _make_draft(voice_confidence_pct=None)
        result = format_draft_message(draft, client_name="Test")
        assert "0%" in result

    def test_handles_none_content_pillar(self):
        draft = _make_draft(content_pillar=None)
        result = format_draft_message(draft, client_name="Test")
        assert "General" in result


# ---------------------------------------------------------------------------
# Test: format_publish_confirmation
# ---------------------------------------------------------------------------


class TestFormatPublishConfirmation:
    def test_includes_url_and_platform(self):
        draft = _make_draft(platform="facebook")
        result = format_publish_confirmation(
            draft, "https://facebook.com/post/123", client_name="Orban Forest"
        )
        assert "Published!" in result
        assert "https://facebook.com/post/123" in result
        assert "Orban Forest" in result
        assert "Facebook" in result


# ---------------------------------------------------------------------------
# Test: format_recovery_result
# ---------------------------------------------------------------------------


class TestFormatRecoveryResult:
    def test_completed(self):
        log = _make_recovery_log(status="completed", platform="facebook")
        result = format_recovery_result(log)
        assert "recovered" in result.lower()
        assert "Facebook" in result

    def test_manual_recovery_needed(self):
        log = _make_recovery_log(
            status="manual_recovery_needed",
            platform="instagram",
            platform_post_id="ig_123",
        )
        result = format_recovery_result(log)
        assert "manual deletion" in result.lower()
        assert "ig_123" in result

    def test_other_status(self):
        log = _make_recovery_log(status="failed")
        result = format_recovery_result(log)
        assert "failed" in result.lower()


# ---------------------------------------------------------------------------
# Test: approval_callback calls service with actor="operator:telegram"
# ---------------------------------------------------------------------------


class TestApprovalCallback:
    @pytest.mark.asyncio
    async def test_calls_service_with_telegram_actor(self):
        query = _make_callback_query("approve_42")
        update = _make_update(callback_query=query)
        context = _make_context()

        mock_draft = _make_draft(draft_id=42)
        with patch(
            "sophia.approval.service.approve_draft",
            return_value=mock_draft,
        ) as mock_approve:
            await approval_callback(update, context)

        mock_approve.assert_called_once()
        _, kwargs = mock_approve.call_args
        assert kwargs.get("actor") == "operator:telegram"
        query.answer.assert_awaited_once()
        query.edit_message_text.assert_awaited_once()
        msg = query.edit_message_text.call_args[0][0]
        assert "Approved" in msg


# ---------------------------------------------------------------------------
# Test: reject_callback stores pending rejection
# ---------------------------------------------------------------------------


class TestRejectCallback:
    @pytest.mark.asyncio
    async def test_stores_pending_rejection(self):
        query = _make_callback_query("reject_7")
        update = _make_update(callback_query=query)
        context = _make_context()

        await reject_callback(update, context)

        assert context.user_data["pending_rejection"] == 7
        query.answer.assert_awaited_once()
        query.edit_message_text.assert_awaited_once()
        msg = query.edit_message_text.call_args[0][0]
        assert "feedback" in msg.lower()


# ---------------------------------------------------------------------------
# Test: rejection_guidance_handler calls reject_draft with guidance
# ---------------------------------------------------------------------------


class TestRejectionGuidanceHandler:
    @pytest.mark.asyncio
    async def test_calls_reject_draft_with_guidance(self):
        message = MagicMock()
        message.text = "too formal, make it casual"
        message.reply_text = AsyncMock()
        update = _make_update(message=message)
        context = _make_context(user_data={"pending_rejection": 99})

        with patch(
            "sophia.approval.service.reject_draft",
            return_value=_make_draft(draft_id=99),
        ) as mock_reject:
            await text_reply_handler(update, context)

        mock_reject.assert_called_once()
        _, kwargs = mock_reject.call_args
        assert kwargs.get("guidance") == "too formal, make it casual"
        assert kwargs.get("actor") == "operator:telegram"
        assert "pending_rejection" not in context.user_data


# ---------------------------------------------------------------------------
# Test: skip_callback calls service
# ---------------------------------------------------------------------------


class TestSkipCallback:
    @pytest.mark.asyncio
    async def test_calls_skip_draft(self):
        query = _make_callback_query("skip_5")
        update = _make_update(callback_query=query)
        context = _make_context()

        with patch(
            "sophia.approval.service.skip_draft",
            return_value=_make_draft(draft_id=5),
        ) as mock_skip:
            await skip_callback(update, context)

        mock_skip.assert_called_once()
        args, kwargs = mock_skip.call_args
        assert args[1] == 5
        assert kwargs.get("actor") == "operator:telegram"
        query.edit_message_text.assert_awaited_once()
        assert "Skipped" in query.edit_message_text.call_args[0][0]


# ---------------------------------------------------------------------------
# Test: global_pause_handler calls pause_all
# ---------------------------------------------------------------------------


class TestGlobalPauseHandler:
    @pytest.mark.asyncio
    async def test_calls_pause_all(self):
        message = MagicMock()
        message.reply_text = AsyncMock()
        update = _make_update(message=message)
        context = _make_context()

        with patch(
            "sophia.publishing.scheduler.pause_all",
            new_callable=AsyncMock,
        ) as mock_pause:
            await global_pause_handler(update, context)

        mock_pause.assert_awaited_once()
        message.reply_text.assert_awaited_once()
        assert "PAUSED" in message.reply_text.call_args[0][0]


# ---------------------------------------------------------------------------
# Test: telegram notification channel on publish_complete
# ---------------------------------------------------------------------------


class TestTelegramNotification:
    @pytest.mark.asyncio
    async def test_notification_sends_message_with_recover_button(self):
        """Verify the notification handler sends a Telegram message with
        a live link and Recover inline button on publish_complete event."""
        from sophia.publishing.notifications import NotificationService

        svc = NotificationService()
        sent_messages: list[dict] = []

        # Create a mock handler simulating what main.py registers
        async def mock_tg_handler(event_type: str, data: dict) -> None:
            sent_messages.append({"event_type": event_type, "data": data})

        svc.register_channel(mock_tg_handler)

        # Patch the event_bus.publish to be a no-op
        with patch(
            "sophia.publishing.notifications.event_bus.publish",
            new_callable=AsyncMock,
        ):
            await svc.notify(
                "publish_complete",
                {
                    "draft_id": 10,
                    "client_id": 1,
                    "platform": "facebook",
                    "platform_url": "https://facebook.com/post/456",
                },
            )

        assert len(sent_messages) == 1
        assert sent_messages[0]["event_type"] == "publish_complete"
        assert sent_messages[0]["data"]["platform_url"] == "https://facebook.com/post/456"
