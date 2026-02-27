"""Content recovery protocol with audit trail.

Handles post-publish recovery for Facebook (via MCP delete_post) and
Instagram (manual fallback since ig-mcp has no delete support).

Recovery protocol:
1. Find the PublishingQueueEntry for the draft
2. Create RecoveryLog entry
3. For immediate urgency:
   a. Facebook: call MCP delete_post tool
   b. Instagram: set status to "manual_recovery_needed"
   c. Transition draft to "recovered" status
   d. Archive internally (keep in DB, never delete)
4. For review urgency: create log with "pending" status
5. Dispatch "recovery_complete" via NotificationService
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from sophia.approval.models import PublishingQueueEntry, RecoveryLog
from sophia.approval.service import transition_draft
from sophia.content.models import ContentDraft
from sophia.publishing.notifications import notify_recovery_complete

logger = logging.getLogger(__name__)


async def recover_content(
    db: Session,
    draft_id: int,
    reason: str,
    urgency: str = "immediate",
    triggered_by: str = "operator:web",
) -> RecoveryLog:
    """Execute content recovery protocol.

    Args:
        db: Database session
        draft_id: ID of the ContentDraft to recover
        reason: Why this content is being recovered
        urgency: "immediate" (execute now) or "review" (pending for operator)
        triggered_by: Interface source (operator:web, operator:telegram, operator:cli, sophia:monitoring)

    Returns:
        RecoveryLog entry with full audit trail
    """
    # Find the draft
    draft = db.query(ContentDraft).filter_by(id=draft_id).first()
    if not draft:
        raise ValueError(f"Draft {draft_id} not found")

    # Find the publishing queue entry
    queue_entry = (
        db.query(PublishingQueueEntry)
        .filter_by(content_draft_id=draft_id)
        .order_by(PublishingQueueEntry.id.desc())
        .first()
    )

    platform = draft.platform
    platform_post_id = queue_entry.platform_post_id if queue_entry else None

    # Create recovery log entry
    log = RecoveryLog(
        content_draft_id=draft_id,
        client_id=draft.client_id,
        platform=platform,
        platform_post_id=platform_post_id,
        urgency=urgency,
        reason=reason,
        status="pending",
        triggered_by=triggered_by,
    )
    db.add(log)
    db.flush()

    if urgency == "immediate":
        log.status = "executing"
        db.flush()

        if platform == "instagram":
            # ig-mcp does not support post deletion
            log.status = "manual_recovery_needed"
            db.flush()
            logger.warning(
                "Instagram recovery requires manual deletion. "
                "Post ID: %s. Please delete manually from Instagram.",
                platform_post_id,
            )
        else:
            # Facebook: call MCP delete_post
            try:
                success = await _dispatch_recovery_mcp(platform, platform_post_id)
                if success:
                    log.status = "completed"
                    log.completed_at = datetime.now(timezone.utc)
                else:
                    log.status = "failed"
            except Exception as e:
                log.status = "failed"
                logger.error(
                    "Recovery MCP dispatch failed for draft %d: %s",
                    draft_id, e,
                )
            db.flush()

        # Transition draft to "recovered" regardless of MCP result
        # (content is archived internally, never deleted from DB)
        transition_draft(db, draft_id, "recovered", actor=triggered_by)
        db.flush()

    # For "review" urgency, log stays "pending" for operator assessment

    # Dispatch notification
    await notify_recovery_complete(log)

    logger.info(
        "Recovery %s for draft %d on %s (status: %s, triggered by: %s)",
        urgency, draft_id, platform, log.status, triggered_by,
    )

    return log


async def _dispatch_recovery_mcp(platform: str, platform_post_id: str) -> bool:
    """Dispatch recovery action to MCP. Returns True if successful.

    Facebook: calls delete_post tool
    Instagram: NOT SUPPORTED by ig-mcp -- returns False immediately
    """
    if platform == "instagram":
        return False  # ig-mcp does not support deletion

    # Facebook: call delete_post via MCP
    raise NotImplementedError(
        f"MCP recovery dispatch for {platform} not wired. "
        "In production, this calls facebook-mcp-server delete_post tool."
    )


def get_recovery_log(
    db: Session, client_id: Optional[int] = None
) -> list[RecoveryLog]:
    """Get recovery log entries, optionally filtered by client."""
    query = db.query(RecoveryLog)
    if client_id is not None:
        query = query.filter_by(client_id=client_id)
    return query.order_by(RecoveryLog.id.desc()).all()
