"""Approval state machine service.

Enforces valid transitions, creates audit logs, sets metadata on approval,
and provides query helpers for the approval queue and health strip.

All functions take db: Session as first arg (Phase 1-3 service pattern).
The service layer is synchronous. Async event publishing happens in the router.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from sophia.approval.models import ApprovalEvent
from sophia.content.models import ContentDraft
from sophia.exceptions import ContentNotFoundError, InvalidTransitionError


# ---------------------------------------------------------------------------
# State machine: {current_status: {allowed_next_statuses}}
# ---------------------------------------------------------------------------

VALID_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"in_review"},
    "in_review": {"approved", "rejected", "skipped"},
    "approved": {"published", "in_review"},  # in_review = re-edit before publish
    "rejected": {"in_review"},  # re-submit after regeneration
    "skipped": {"in_review"},  # operator reconsiders
    "published": {"recovered"},  # content recovery
    "recovered": {"in_review"},  # replacement draft
}


# ---------------------------------------------------------------------------
# Core transition function
# ---------------------------------------------------------------------------


def transition_draft(
    db: Session,
    draft_id: int,
    new_status: str,
    actor: str = "operator",
    **kwargs,
) -> ContentDraft:
    """Validate and execute a state transition on a content draft.

    Creates an ApprovalEvent audit record for every transition.
    Does NOT call event_bus (sync function -- router handles async events).

    Raises:
        ContentNotFoundError: if draft_id does not exist
        InvalidTransitionError: if the transition is not in VALID_TRANSITIONS
    """
    draft = db.query(ContentDraft).filter(ContentDraft.id == draft_id).first()
    if draft is None:
        raise ContentNotFoundError(
            detail=f"Draft ID {draft_id} not found",
        )

    old_status = draft.status
    allowed = VALID_TRANSITIONS.get(old_status, set())

    if new_status not in allowed:
        raise InvalidTransitionError(
            message=f"Cannot transition from '{old_status}' to '{new_status}'",
            detail=f"Allowed transitions from '{old_status}': {sorted(allowed)}",
        )

    # Apply transition
    draft.status = new_status

    # Create audit log
    audit = ApprovalEvent(
        content_draft_id=draft.id,
        client_id=draft.client_id,
        action=new_status,
        actor=actor,
        old_status=old_status,
        new_status=new_status,
        details=kwargs.get("details"),
    )
    db.add(audit)
    db.flush()

    # Capture approval decision trace (optional analytics integration)
    try:
        from sophia.analytics.decision_trace import capture_approval_decision
        capture_approval_decision(db, draft.id, draft.client_id, new_status, actor)
    except ImportError:
        pass

    return draft


# ---------------------------------------------------------------------------
# High-level approval actions
# ---------------------------------------------------------------------------


def approve_draft(
    db: Session,
    draft_id: int,
    publish_mode: str = "auto",
    custom_post_time: Optional[datetime] = None,
    actor: str = "operator:web",
) -> ContentDraft:
    """Approve a draft: transition to 'approved', set metadata."""
    details = {"publish_mode": publish_mode}
    if custom_post_time:
        details["custom_post_time"] = custom_post_time.isoformat()

    draft = transition_draft(
        db, draft_id, "approved", actor=actor, details=details
    )
    draft.approved_at = datetime.now(timezone.utc)
    draft.approved_by = actor
    draft.publish_mode = publish_mode
    if custom_post_time:
        draft.custom_post_time = custom_post_time
    db.flush()
    return draft


def reject_draft(
    db: Session,
    draft_id: int,
    tags: Optional[list[str]] = None,
    guidance: Optional[str] = None,
    actor: str = "operator:web",
) -> ContentDraft:
    """Reject a draft: transition to 'rejected'. Draft stays in DB for learning."""
    details = {}
    if tags:
        details["tags"] = tags
    if guidance:
        details["guidance"] = guidance

    draft = transition_draft(
        db, draft_id, "rejected", actor=actor, details=details or None
    )
    db.flush()
    return draft


def edit_draft(
    db: Session,
    draft_id: int,
    new_copy: str,
    custom_post_time: Optional[datetime] = None,
    actor: str = "operator:web",
) -> ContentDraft:
    """Edit a draft: update copy, record edit, then approve."""
    # Build edit record
    edit_record = {
        "actor": actor,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "old_copy_preview": None,  # filled below
        "new_copy_preview": new_copy[:200],
    }

    # Fetch draft to capture old copy before transitioning
    draft = db.query(ContentDraft).filter(ContentDraft.id == draft_id).first()
    if draft is None:
        raise ContentNotFoundError(detail=f"Draft ID {draft_id} not found")

    edit_record["old_copy_preview"] = draft.copy[:200]

    # Update copy
    draft.copy = new_copy

    # Append to operator_edits
    edits = list(draft.operator_edits or [])
    edits.append(edit_record)
    draft.operator_edits = edits

    # Transition to approved
    details = {"edited": True}
    if custom_post_time:
        details["custom_post_time"] = custom_post_time.isoformat()

    result = transition_draft(
        db, draft_id, "approved", actor=actor, details=details
    )

    # Set approval metadata
    result.approved_at = datetime.now(timezone.utc)
    result.approved_by = actor
    if custom_post_time:
        result.custom_post_time = custom_post_time
    db.flush()
    return result


def skip_draft(
    db: Session,
    draft_id: int,
    actor: str = "operator:web",
) -> ContentDraft:
    """Skip a draft: transition to 'skipped'."""
    return transition_draft(db, draft_id, "skipped", actor=actor)


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


def get_approval_queue(
    db: Session,
    client_id: Optional[int] = None,
    status: Optional[str] = None,
) -> list[ContentDraft]:
    """Query drafts for the approval queue.

    Defaults to in_review status. Optionally filters by client_id.
    """
    query = db.query(ContentDraft)
    if client_id is not None:
        query = query.filter(ContentDraft.client_id == client_id)
    if status:
        query = query.filter(ContentDraft.status == status)
    else:
        query = query.filter(ContentDraft.status == "in_review")
    return query.order_by(ContentDraft.id).all()


def get_health_strip_data(db: Session) -> dict:
    """Return counts by client status for the health strip.

    Returns dict with client counts grouped by operational state
    (cruising/calibrating/attention) and total posts remaining today.
    """
    from sqlalchemy import func

    # Count in_review drafts (attention needed)
    attention_count = (
        db.query(func.count(func.distinct(ContentDraft.client_id)))
        .filter(ContentDraft.status == "in_review")
        .scalar()
        or 0
    )

    # Count approved drafts (cruising -- ready to publish)
    cruising_count = (
        db.query(func.count(func.distinct(ContentDraft.client_id)))
        .filter(ContentDraft.status == "approved")
        .scalar()
        or 0
    )

    # Total posts waiting for approval
    posts_in_review = (
        db.query(func.count(ContentDraft.id))
        .filter(ContentDraft.status == "in_review")
        .scalar()
        or 0
    )

    return {
        "attention": attention_count,
        "cruising": cruising_count,
        "calibrating": 0,  # placeholder for future calibration tracking
        "posts_in_review": posts_in_review,
    }
