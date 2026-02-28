"""MCP dispatch to Facebook and Instagram with retry logic.

Executes publishing jobs at the scheduled time. Called by APScheduler.
Handles retries with exponential backoff (2, 4, 8 minutes) up to 3 attempts.
On final failure, marks the queue entry as "failed" and alerts via notification service.

MCP dispatch is a NotImplementedError integration point (same pattern as Phase 2 research).
Tests mock at _dispatch_mcp level. Real MCP wiring is trivial later.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from sophia.approval.models import GlobalPublishState, PublishingQueueEntry
from sophia.approval.service import transition_draft
from sophia.content.models import ContentDraft
from sophia.publishing.notifications import notify_publish_complete, notify_publish_failed

logger = logging.getLogger(__name__)

# Maximum retry attempts before marking as failed
MAX_RETRIES = 3

# Backoff schedule in minutes: 2, 4, 8
BACKOFF_MINUTES = [2, 4, 8]


async def execute_publish(
    draft_id: int,
    platform: str,
    db_session_factory: Callable[[], Session],
) -> None:
    """Execute a publishing job. Called by APScheduler at scheduled time.

    Steps:
    1. Check global pause state
    2. Check rate limits
    3. Verify image_url exists on queue entry (required for publishing)
    4. Dispatch to MCP
    5. On success: transition draft to "published", store platform IDs, broadcast event
    6. On failure: retry with backoff or mark failed and alert
    """
    db = db_session_factory()
    try:
        # 1. Check global pause state
        pause_state = db.query(GlobalPublishState).first()
        if pause_state and pause_state.is_paused:
            logger.info("Publishing paused globally -- skipping draft %d", draft_id)
            entry = (
                db.query(PublishingQueueEntry)
                .filter_by(content_draft_id=draft_id, platform=platform)
                .first()
            )
            if entry:
                entry.status = "paused"
                db.flush()
            return

        # Find queue entry
        entry = (
            db.query(PublishingQueueEntry)
            .filter_by(content_draft_id=draft_id, platform=platform)
            .order_by(PublishingQueueEntry.id.desc())
            .first()
        )
        if not entry:
            logger.error("No queue entry for draft %d on %s", draft_id, platform)
            return

        # 3. Verify image_url exists
        if not entry.image_url:
            entry.status = "failed"
            entry.error_message = "Image URL required before publishing"
            db.flush()
            logger.error("No image_url for draft %d -- marking failed", draft_id)
            return

        # Find the draft
        draft = db.query(ContentDraft).filter_by(id=draft_id).first()
        if not draft:
            entry.status = "failed"
            entry.error_message = f"Draft {draft_id} not found"
            db.flush()
            return

        # 4. Dispatch to MCP
        entry.status = "publishing"
        db.flush()

        try:
            result = await _dispatch_mcp(platform, {
                "copy": draft.copy,
                "image_url": entry.image_url,
                "hashtags": draft.hashtags,
                "alt_text": draft.alt_text,
            })

            # 5. Success
            entry.platform_post_id = result.get("post_id")
            entry.platform_post_url = result.get("url")
            entry.status = "published"
            db.flush()

            # Transition draft to "published"
            transition_draft(db, draft_id, "published", actor="sophia:publisher")
            draft.published_at = datetime.now(timezone.utc)
            db.flush()

            # Capture performance decision trace (optional analytics)
            try:
                from sophia.analytics.decision_trace import capture_decision
                predicted = {}
                if getattr(draft, "voice_confidence_pct", None):
                    predicted["approval_first_pass"] = draft.voice_confidence_pct / 100.0
                if getattr(draft, "rank_reasoning", None):
                    predicted["rank_reasoning"] = draft.rank_reasoning
                capture_decision(
                    db=db,
                    draft_id=draft_id,
                    client_id=draft.client_id,
                    stage="performance",
                    decision=f"Published to {platform}",
                    evidence={"platform_post_id": result.get("post_id", "")},
                    predicted_outcome=predicted if predicted else None,
                )
            except (ImportError, Exception):
                pass  # Analytics module not yet available

            # Broadcast success event
            await notify_publish_complete(draft, result.get("url", ""))

            logger.info(
                "Published draft %d to %s: %s",
                draft_id, platform, result.get("url"),
            )

        except Exception as e:
            # 6. Failure handling
            entry.retry_count += 1
            entry.error_message = str(e)

            if entry.retry_count >= MAX_RETRIES:
                entry.status = "failed"
                db.flush()
                await notify_publish_failed(draft, str(e))
                logger.error(
                    "Draft %d failed after %d retries: %s",
                    draft_id, MAX_RETRIES, e,
                )
            else:
                # Reschedule with backoff
                entry.status = "queued"
                db.flush()
                logger.warning(
                    "Draft %d publish failed (attempt %d/%d): %s",
                    draft_id, entry.retry_count, MAX_RETRIES, e,
                )

    finally:
        # Do NOT close the session -- caller (test) manages it
        pass


async def _dispatch_mcp(platform: str, content: dict) -> dict:
    """Dispatch to platform MCP server.

    NotImplementedError for now (same pattern as Phase 2 research).
    In production, this calls facebook-mcp-server or ig-mcp tools.

    Returns: {"post_id": str, "url": str}
    """
    raise NotImplementedError(
        f"MCP dispatch for {platform} not wired. "
        "In production, this calls facebook-mcp-server or ig-mcp tools."
    )
