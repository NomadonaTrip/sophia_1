"""Message formatters for Telegram content approval.

Formats ContentDraft objects into readable Telegram messages with
Markdown formatting for mobile review. Also formats publish
confirmations and recovery results.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from sophia.approval.models import RecoveryLog
    from sophia.content.models import ContentDraft


def _format_time(dt: Optional[datetime]) -> str:
    """Format a datetime for display, or return 'Not scheduled'."""
    if dt is None:
        return "Not scheduled"
    return dt.strftime("%b %d, %I:%M %p")


def format_draft_message(draft: "ContentDraft", client_name: str = "") -> str:
    """Format a content draft for Telegram display.

    One message per content option. Shows: client name, platform,
    post copy, image prompt description, voice match %, content pillar.
    Uses Markdown formatting for readability on mobile.

    Args:
        draft: The ContentDraft to format.
        client_name: Client name to display (since ContentDraft only has client_id).
    """
    display_name = client_name or f"Client #{draft.client_id}"
    voice_pct = draft.voice_confidence_pct or 0.0
    pillar = draft.content_pillar or "General"
    scheduled = _format_time(draft.suggested_post_time)

    return (
        f"*{display_name}* | {draft.platform.title()}\n\n"
        f"{draft.copy}\n\n"
        f"Image: _{draft.image_prompt}_\n"
        f"Voice: {voice_pct:.0f}% match | "
        f"Pillar: {pillar}\n"
        f"Scheduled: {scheduled}"
    )


def format_publish_confirmation(
    draft: "ContentDraft", platform_url: str, client_name: str = ""
) -> str:
    """Format post-publish confirmation with live link."""
    display_name = client_name or f"Client #{draft.client_id}"
    return (
        f"Published! {display_name} on {draft.platform.title()}\n"
        f"{platform_url}"
    )


def format_recovery_result(log: "RecoveryLog") -> str:
    """Format recovery result notification."""
    if log.status == "completed":
        return (
            f"Post recovered from {log.platform.title()}. Archived internally."
        )
    elif log.status == "manual_recovery_needed":
        return (
            f"Instagram post requires manual deletion.\n"
            f"Post ID: {log.platform_post_id}\n"
            f"Please delete from the Instagram app."
        )
    return f"Recovery status: {log.status}"
