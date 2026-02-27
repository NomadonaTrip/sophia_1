"""Notification dispatch service for publishing events.

Dispatches events to all registered notification channels:
- SSE event bus (always active)
- Telegram bot (when registered by Plan 04-05)

This is the single dispatch point. The executor and recovery modules
call notification_service.notify(), not event_bus.publish() directly.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Coroutine

from sophia.approval.events import event_bus

logger = logging.getLogger(__name__)


class NotificationService:
    """Dispatches publishing events to SSE event bus + all registered channels.

    Channels are async callables: (event_type: str, data: dict) -> None.
    Channel failures are logged but never break the publishing pipeline.
    """

    def __init__(self) -> None:
        self._channels: list[Callable[..., Coroutine[Any, Any, None]]] = []

    def register_channel(
        self, callback: Callable[..., Coroutine[Any, Any, None]]
    ) -> None:
        """Register a notification callback (e.g., Telegram send_message wrapper)."""
        self._channels.append(callback)

    async def notify(self, event_type: str, data: dict) -> None:
        """Dispatch to SSE event bus + all registered channels.

        Channel failures are caught and logged -- they must never break publishing.
        """
        # Always publish to SSE event bus
        await event_bus.publish(event_type, data)

        # Dispatch to registered channels
        for channel in self._channels:
            try:
                await channel(event_type, data)
            except Exception:
                logger.warning(
                    "Notification channel failed for event %s", event_type,
                    exc_info=True,
                )


# Module-level singleton
notification_service = NotificationService()


async def notify_publish_complete(draft: Any, platform_url: str) -> None:
    """Notify all channels of successful publish."""
    await notification_service.notify(
        "publish_complete",
        {
            "draft_id": draft.id,
            "client_id": draft.client_id,
            "platform": draft.platform,
            "platform_url": platform_url,
        },
    )


async def notify_publish_failed(draft: Any, error: str) -> None:
    """Notify all channels of publish failure after retries exhausted."""
    await notification_service.notify(
        "publish_failed",
        {
            "draft_id": draft.id,
            "client_id": draft.client_id,
            "platform": draft.platform,
            "error": error,
        },
    )


async def notify_recovery_complete(recovery_log: Any) -> None:
    """Notify all channels of recovery completion."""
    await notification_service.notify(
        "recovery_complete",
        {
            "draft_id": recovery_log.content_draft_id,
            "client_id": recovery_log.client_id,
            "platform": recovery_log.platform,
            "status": recovery_log.status,
        },
    )
