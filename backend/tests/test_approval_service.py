"""Tests for approval state machine, event bus, and audit logging.

Covers all valid and invalid transitions, metadata setting on approval,
rejection/edit/skip semantics, recovery flow, audit trail creation,
and event bus publish/subscribe.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from sophia.approval.events import ApprovalEventBus, event_bus
from sophia.approval.models import (
    ApprovalEvent,
    GlobalPublishState,
    NotificationPreference,
    PublishingQueueEntry,
    RecoveryLog,
)
from sophia.approval.service import (
    VALID_TRANSITIONS,
    approve_draft,
    edit_draft,
    get_approval_queue,
    reject_draft,
    skip_draft,
    transition_draft,
)
from sophia.content.models import ContentDraft
from sophia.exceptions import ContentNotFoundError, InvalidTransitionError


# =============================================================================
# Helpers
# =============================================================================


def _make_draft(
    db_session,
    client_id: int,
    status: str = "draft",
    copy: str = "Test content for approval.",
    **kwargs,
) -> ContentDraft:
    """Create and persist a ContentDraft for testing."""
    defaults = dict(
        client_id=client_id,
        platform="instagram",
        content_type="feed",
        copy=copy,
        image_prompt="Test image prompt",
        image_ratio="1:1",
        status=status,
        gate_status="passed",
    )
    defaults.update(kwargs)
    draft = ContentDraft(**defaults)
    db_session.add(draft)
    db_session.flush()
    return draft


# =============================================================================
# Test 1: Valid transitions
# =============================================================================


class TestValidTransitions:
    """Test that all valid state transitions succeed."""

    def test_draft_to_in_review(self, db_session, sample_client):
        draft = _make_draft(db_session, sample_client.id, status="draft")
        result = transition_draft(db_session, draft.id, "in_review")
        assert result.status == "in_review"

    def test_in_review_to_approved(self, db_session, sample_client):
        draft = _make_draft(db_session, sample_client.id, status="in_review")
        result = transition_draft(db_session, draft.id, "approved")
        assert result.status == "approved"

    def test_in_review_to_rejected(self, db_session, sample_client):
        draft = _make_draft(db_session, sample_client.id, status="in_review")
        result = transition_draft(db_session, draft.id, "rejected")
        assert result.status == "rejected"

    def test_in_review_to_skipped(self, db_session, sample_client):
        draft = _make_draft(db_session, sample_client.id, status="in_review")
        result = transition_draft(db_session, draft.id, "skipped")
        assert result.status == "skipped"


# =============================================================================
# Test 2: Invalid transition draft->published (APPR-06)
# =============================================================================


class TestInvalidTransitionDraftToPublished:
    """APPR-06: Sophia NEVER publishes without explicit approval."""

    def test_draft_to_published_raises(self, db_session, sample_client):
        draft = _make_draft(db_session, sample_client.id, status="draft")
        with pytest.raises(InvalidTransitionError):
            transition_draft(db_session, draft.id, "published")


# =============================================================================
# Test 3: Invalid transition draft->approved (must go through in_review)
# =============================================================================


class TestInvalidTransitionDraftToApproved:
    """Cannot skip in_review step."""

    def test_draft_to_approved_raises(self, db_session, sample_client):
        draft = _make_draft(db_session, sample_client.id, status="draft")
        with pytest.raises(InvalidTransitionError):
            transition_draft(db_session, draft.id, "approved")


# =============================================================================
# Test 4: approve_draft sets metadata
# =============================================================================


class TestApproveMetadata:
    """Approving sets approved_at, approved_by, and publish_mode."""

    def test_approve_sets_metadata(self, db_session, sample_client):
        draft = _make_draft(db_session, sample_client.id, status="in_review")
        result = approve_draft(
            db_session, draft.id, publish_mode="auto", actor="operator:web"
        )
        assert result.status == "approved"
        assert result.approved_at is not None
        assert result.approved_by == "operator:web"
        assert result.publish_mode == "auto"


# =============================================================================
# Test 5: reject preserves draft
# =============================================================================


class TestRejectPreservesDraft:
    """Rejected drafts stay in DB for learning; status set to 'rejected'."""

    def test_reject_preserves_draft(self, db_session, sample_client):
        draft = _make_draft(db_session, sample_client.id, status="in_review")
        result = reject_draft(
            db_session, draft.id, tags=["off-brand"], guidance="Too casual"
        )
        assert result.status == "rejected"
        # Draft still in DB
        still_there = (
            db_session.query(ContentDraft)
            .filter(ContentDraft.id == draft.id)
            .first()
        )
        assert still_there is not None
        assert still_there.status == "rejected"


# =============================================================================
# Test 6: edit_draft updates copy
# =============================================================================


class TestEditDraft:
    """Editing updates copy text and records operator_edits JSON."""

    def test_edit_draft_updates_copy(self, db_session, sample_client):
        draft = _make_draft(db_session, sample_client.id, status="in_review")
        result = edit_draft(db_session, draft.id, new_copy="Updated content here")
        assert result.copy == "Updated content here"
        assert result.status == "approved"
        assert result.operator_edits is not None
        assert len(result.operator_edits) == 1


# =============================================================================
# Test 7: skip_draft
# =============================================================================


class TestSkipDraft:
    """Skipping sets status to 'skipped'."""

    def test_skip_draft(self, db_session, sample_client):
        draft = _make_draft(db_session, sample_client.id, status="in_review")
        result = skip_draft(db_session, draft.id)
        assert result.status == "skipped"


# =============================================================================
# Test 8: Recovery transition
# =============================================================================


class TestRecoveryTransition:
    """published->recovered is a valid transition."""

    def test_recovery_transition(self, db_session, sample_client):
        draft = _make_draft(db_session, sample_client.id, status="published")
        result = transition_draft(db_session, draft.id, "recovered")
        assert result.status == "recovered"


# =============================================================================
# Test 9: Audit log created on every transition
# =============================================================================


class TestAuditLogCreated:
    """Every transition creates an ApprovalEvent record."""

    def test_audit_log_created(self, db_session, sample_client):
        draft = _make_draft(db_session, sample_client.id, status="draft")
        transition_draft(db_session, draft.id, "in_review", actor="operator:cli")

        events = (
            db_session.query(ApprovalEvent)
            .filter(ApprovalEvent.content_draft_id == draft.id)
            .all()
        )
        assert len(events) == 1
        assert events[0].action == "in_review"
        assert events[0].actor == "operator:cli"
        assert events[0].old_status == "draft"
        assert events[0].new_status == "in_review"


# =============================================================================
# Test 10: Event bus publish/subscribe
# =============================================================================


class TestEventBusPublish:
    """State transitions publish to event bus (mock subscriber)."""

    def test_event_bus_publish(self):
        bus = ApprovalEventBus()
        received = []

        async def _run():
            queue = asyncio.Queue()
            bus._subscribers.append(queue)
            await bus.publish("approval", {"draft_id": 1, "new_status": "approved"})
            event = await asyncio.wait_for(queue.get(), timeout=1.0)
            received.append(event)

        asyncio.run(_run())
        assert len(received) == 1
        assert received[0]["type"] == "approval"
        assert received[0]["data"]["draft_id"] == 1

    def test_event_bus_subscribe(self):
        bus = ApprovalEventBus()
        received = []

        async def _run():
            gen = bus.subscribe()
            # Publish before consuming
            await bus.publish("test_event", {"key": "value"})
            event = await asyncio.wait_for(gen.__anext__(), timeout=1.0)
            received.append(event)
            await gen.aclose()

        asyncio.run(_run())
        assert len(received) == 1
        assert received[0]["type"] == "test_event"


# =============================================================================
# Test 11: approve with custom time
# =============================================================================


class TestApproveWithCustomTime:
    """Operator can override suggested_post_time."""

    def test_approve_with_custom_time(self, db_session, sample_client):
        draft = _make_draft(db_session, sample_client.id, status="in_review")
        custom_time = datetime(2026, 3, 1, 14, 0, tzinfo=timezone.utc)
        result = approve_draft(
            db_session, draft.id, custom_post_time=custom_time, actor="operator:web"
        )
        assert result.custom_post_time == custom_time


# =============================================================================
# Test 12: approve sets publish_mode
# =============================================================================


class TestApprovePublishMode:
    """Publish mode can be auto or manual per approval."""

    def test_approve_sets_auto_mode(self, db_session, sample_client):
        draft = _make_draft(db_session, sample_client.id, status="in_review")
        result = approve_draft(db_session, draft.id, publish_mode="auto")
        assert result.publish_mode == "auto"

    def test_approve_sets_manual_mode(self, db_session, sample_client):
        draft = _make_draft(db_session, sample_client.id, status="in_review")
        result = approve_draft(db_session, draft.id, publish_mode="manual")
        assert result.publish_mode == "manual"
