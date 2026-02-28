"""Tests for approval REST router endpoints and SSE streaming.

Uses FastAPI TestClient with DB dependency override. Validates
HTTP status codes, response bodies, SSE content type, and error
handling for invalid transitions and missing drafts.
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sophia.approval.events import ApprovalEventBus, event_bus
from sophia.approval.models import (
    ApprovalEvent,
    GlobalPublishState,
    RecoveryLog,
)
from sophia.approval.router import approval_router, events_router, _get_db
from sophia.content.models import ContentDraft


# =============================================================================
# Helpers
# =============================================================================


def _make_draft(
    db_session,
    client_id: int,
    status: str = "draft",
    copy: str = "Test content for router.",
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


@pytest.fixture
def app(db_session):
    """Create FastAPI app with DB dependency override."""
    test_app = FastAPI()
    test_app.include_router(approval_router)
    test_app.include_router(events_router)

    def override_db():
        yield db_session

    test_app.dependency_overrides[_get_db] = override_db
    return test_app


@pytest.fixture
def client(app):
    """TestClient for the approval API."""
    return TestClient(app)


# =============================================================================
# Test 1: approve endpoint
# =============================================================================


class TestApproveEndpoint:
    def test_approve_returns_200(self, client, db_session, sample_client):
        draft = _make_draft(db_session, sample_client.id, status="in_review")
        resp = client.post(
            f"/api/approval/drafts/{draft.id}/approve",
            json={"publish_mode": "auto"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["draft_id"] == draft.id
        assert data["old_status"] == "in_review"
        assert data["new_status"] == "approved"


# =============================================================================
# Test 2: reject endpoint
# =============================================================================


class TestRejectEndpoint:
    def test_reject_returns_200(self, client, db_session, sample_client):
        draft = _make_draft(db_session, sample_client.id, status="in_review")
        resp = client.post(
            f"/api/approval/drafts/{draft.id}/reject",
            json={"tags": ["off-brand"], "guidance": "Too casual for client"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["new_status"] == "rejected"


# =============================================================================
# Test 3: edit endpoint
# =============================================================================


class TestEditEndpoint:
    def test_edit_returns_200(self, client, db_session, sample_client):
        draft = _make_draft(db_session, sample_client.id, status="in_review")
        resp = client.post(
            f"/api/approval/drafts/{draft.id}/edit",
            json={"copy": "Updated content here"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["new_status"] == "approved"


# =============================================================================
# Test 4: skip endpoint
# =============================================================================


class TestSkipEndpoint:
    def test_skip_returns_200(self, client, db_session, sample_client):
        draft = _make_draft(db_session, sample_client.id, status="in_review")
        resp = client.post(f"/api/approval/drafts/{draft.id}/skip")
        assert resp.status_code == 200
        data = resp.json()
        assert data["new_status"] == "skipped"


# =============================================================================
# Test 5: invalid transition returns 409
# =============================================================================


class TestInvalidTransitionReturns409:
    def test_invalid_transition_returns_409(self, client, db_session, sample_client):
        draft = _make_draft(db_session, sample_client.id, status="draft")
        resp = client.post(
            f"/api/approval/drafts/{draft.id}/approve",
            json={"publish_mode": "auto"},
        )
        assert resp.status_code == 409


# =============================================================================
# Test 6: draft not found returns 404
# =============================================================================


class TestDraftNotFoundReturns404:
    def test_not_found_returns_404(self, client):
        resp = client.post(
            "/api/approval/drafts/99999/approve",
            json={"publish_mode": "auto"},
        )
        assert resp.status_code == 404


# =============================================================================
# Test 7: approval queue endpoint
# =============================================================================


class TestApprovalQueueEndpoint:
    def test_queue_returns_in_review_drafts(self, client, db_session, sample_client):
        _make_draft(db_session, sample_client.id, status="in_review")
        _make_draft(db_session, sample_client.id, status="draft")
        resp = client.get("/api/approval/queue")
        assert resp.status_code == 200
        data = resp.json()
        # Only the in_review draft
        assert len(data) == 1


# =============================================================================
# Test 8: health strip endpoint
# =============================================================================


class TestHealthStripEndpoint:
    def test_health_strip_returns_counts(self, client, db_session, sample_client):
        _make_draft(db_session, sample_client.id, status="in_review")
        _make_draft(db_session, sample_client.id, status="approved")
        resp = client.get("/api/approval/health-strip")
        assert resp.status_code == 200
        data = resp.json()
        assert "attention" in data
        assert "cruising" in data
        assert "posts_in_review" in data


# =============================================================================
# Test 9: SSE endpoint returns event-stream content type
# =============================================================================


class TestSSEEndpoint:
    def test_sse_endpoint_returns_event_source(self, app):
        """GET /api/events returns text/event-stream content type."""
        # Use a mock event bus that yields one event then stops
        test_bus = ApprovalEventBus()

        import asyncio

        async def _fake_subscribe():
            yield {"type": "test", "data": {"msg": "hello"}}

        with patch(
            "sophia.approval.router.event_bus"
        ) as mock_bus:
            mock_bus.subscribe = _fake_subscribe
            test_client = TestClient(app)
            with test_client.stream("GET", "/api/events") as resp:
                assert resp.status_code == 200
                content_type = resp.headers.get("content-type", "")
                assert "text/event-stream" in content_type


# =============================================================================
# Test 10: global pause/resume toggle
# =============================================================================


class TestGlobalPauseToggle:
    def test_pause_and_resume(self, client, db_session):
        # Ensure GlobalPublishState exists
        state = GlobalPublishState(is_paused=False)
        db_session.add(state)
        db_session.flush()

        # Pause
        resp = client.post("/api/approval/pause")
        assert resp.status_code == 200
        assert resp.json()["is_paused"] is True

        # Resume
        resp = client.post("/api/approval/resume")
        assert resp.status_code == 200
        assert resp.json()["is_paused"] is False


# =============================================================================
# Test 11: recover endpoint
# =============================================================================


class TestRecoverEndpoint:
    def test_recover_returns_recovery_status(self, client, db_session, sample_client):
        draft = _make_draft(db_session, sample_client.id, status="published")
        resp = client.post(
            f"/api/approval/drafts/{draft.id}/recover",
            json={"reason": "Client complaint about typo", "urgency": "immediate"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["draft_id"] == draft.id
        assert data["status"] == "recovered"


# =============================================================================
# Test 12: recover non-published returns 409
# =============================================================================


# =============================================================================
# Test 12b: upload image sets draft.image_url
# =============================================================================


class TestUploadImageSetsDraftImageUrl:
    def test_upload_sets_image_url(self, client, db_session, sample_client):
        """Upload endpoint persists image_url on the ContentDraft."""
        draft = _make_draft(db_session, sample_client.id, status="in_review")
        assert draft.image_url is None

        import io

        file_content = b"fake image bytes"
        resp = client.post(
            f"/api/approval/drafts/{draft.id}/upload-image",
            files={"file": ("test.png", io.BytesIO(file_content), "image/png")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "image_url" in data
        assert data["image_url"].endswith(".png")

        # Verify DB was updated
        db_session.refresh(draft)
        assert draft.image_url is not None
        assert "test.png" in draft.image_url


class TestRecoverNonPublishedReturns409:
    def test_recover_nonpublished_returns_409(self, client, db_session, sample_client):
        draft = _make_draft(db_session, sample_client.id, status="in_review")
        resp = client.post(
            f"/api/approval/drafts/{draft.id}/recover",
            json={"reason": "Trying to recover non-published", "urgency": "immediate"},
        )
        assert resp.status_code == 409
