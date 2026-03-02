"""Tests for observer, judge, and auto-approval modules.

Covers:
- Observer: fresh client, client with content, research freshness
- Judge: high confidence, low voice, failed gate, sensitive content,
         low approval rate, rationale lists failures
- Auto-approval: burn-in, past burn-in, suspension, disabled, signals dict
"""

from datetime import datetime, timedelta, timezone

import pytest

from sophia.content.models import ContentDraft
from sophia.orchestrator.auto_approval import (
    check_burn_in_status,
    record_auto_approval_outcome,
    should_auto_approve,
)
from sophia.orchestrator.judge import DraftJudgment, evaluate_draft_confidence
from sophia.orchestrator.models import AutoApprovalConfig, SpecialistAgent
from sophia.orchestrator.observer import ClientObservation, observe_client_state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_naive():
    """Current UTC time as naive datetime (SQLite pattern)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _make_config(db, client_id, **overrides):
    """Create an AutoApprovalConfig with sensible defaults."""
    defaults = {
        "client_id": client_id,
        "enabled": True,
        "min_voice_confidence": 0.75,
        "require_all_gates_pass": True,
        "max_content_risk": "safe",
        "min_historical_approval_rate": 0.80,
        "burn_in_cycles": 15,
        "completed_cycles": 20,
    }
    defaults.update(overrides)
    config = AutoApprovalConfig(**defaults)
    db.add(config)
    db.flush()
    return config


def _make_observation(client_id=1, **overrides):
    """Create a ClientObservation with defaults for testing."""
    defaults = {
        "client_id": client_id,
        "client_name": "Test Client",
        "last_post_date": None,
        "days_since_last_post": 9999,
        "pending_approvals": 0,
        "recent_engagement_trend": "stable",
        "research_freshness_hours": None,
        "needs_research": True,
        "active_anomalies": 0,
        "approval_rate_30d": 0.90,
        "completed_cycles": 20,
    }
    defaults.update(overrides)
    return ClientObservation(**defaults)


def _make_draft(db, client_id, **overrides):
    """Create a ContentDraft with required fields."""
    defaults = {
        "client_id": client_id,
        "platform": "facebook",
        "content_type": "feed",
        "copy": "Test post content",
        "image_prompt": "A photo of a test",
        "image_ratio": "1:1",
        "status": "pending_review",
        "voice_confidence_pct": 85.0,
        "gate_report": {
            "gates": [
                {"name": "length", "status": "passed"},
                {"name": "readability", "status": "passed"},
                {"name": "cliche", "status": "passed"},
                {"name": "sensitivity", "status": "passed"},
                {"name": "voice", "status": "passed"},
            ]
        },
    }
    defaults.update(overrides)
    draft = ContentDraft(**defaults)
    db.add(draft)
    db.flush()
    return draft


def _make_specialist(db, client_id, **overrides):
    """Create a SpecialistAgent for testing."""
    defaults = {
        "client_id": client_id,
        "specialty": "general",
        "state_json": {},
        "is_active": True,
        "total_cycles": 0,
        "approval_rate": 0.0,
        "false_positive_count": 0,
    }
    defaults.update(overrides)
    agent = SpecialistAgent(**defaults)
    db.add(agent)
    db.flush()
    return agent


# ============================================================================
# Observer Tests
# ============================================================================


class TestObserver:
    """Tests for observe_client_state."""

    def test_observe_fresh_client(self, db_session, sample_client):
        """Fresh client with no history returns safe defaults."""
        obs = observe_client_state(db_session, sample_client.id)

        assert obs.client_id == sample_client.id
        assert obs.client_name == sample_client.name
        assert obs.last_post_date is None
        assert obs.days_since_last_post >= 9999
        assert obs.pending_approvals == 0
        assert obs.needs_research is True
        assert obs.recent_engagement_trend == "stable"
        assert obs.approval_rate_30d == 0.0

    def test_observe_client_with_content(self, db_session, sample_client):
        """Client with published and pending content shows correct counts."""
        # Published draft
        _make_draft(
            db_session,
            sample_client.id,
            status="published",
            copy="Published post",
        )
        # Pending review draft
        _make_draft(
            db_session,
            sample_client.id,
            status="pending_review",
            copy="Pending post",
        )
        db_session.flush()

        obs = observe_client_state(db_session, sample_client.id)

        assert obs.last_post_date is not None
        assert obs.pending_approvals == 1
        assert obs.days_since_last_post >= 0

    def test_observe_research_freshness(self, db_session, sample_client):
        """Research freshness is computed from most recent finding."""
        try:
            from sophia.research.models import ResearchFinding
        except ImportError:
            pytest.skip("Research models not available")

        # Create a finding 12 hours ago
        finding_time = _now_naive() - timedelta(hours=12)
        finding = ResearchFinding(
            client_id=sample_client.id,
            finding_type="news",
            topic="Test topic",
            summary="Test summary",
            created_at=finding_time,
        )
        db_session.add(finding)
        db_session.flush()

        obs = observe_client_state(db_session, sample_client.id)
        assert obs.research_freshness_hours is not None
        assert obs.research_freshness_hours < 13.0  # approx 12 hours
        assert obs.needs_research is False

        # Delete the recent finding and create an old one (30 hours ago)
        db_session.delete(finding)
        old_finding = ResearchFinding(
            client_id=sample_client.id,
            finding_type="news",
            topic="Old topic",
            summary="Old summary",
            created_at=_now_naive() - timedelta(hours=30),
        )
        db_session.add(old_finding)
        db_session.flush()

        obs2 = observe_client_state(db_session, sample_client.id)
        assert obs2.research_freshness_hours is not None
        assert obs2.research_freshness_hours > 24.0
        assert obs2.needs_research is True


# ============================================================================
# Judge Tests
# ============================================================================


class TestJudge:
    """Tests for evaluate_draft_confidence."""

    def test_judge_high_confidence_draft(self, db_session, sample_client):
        """High quality draft with all signals passing gets auto-approved."""
        draft = _make_draft(
            db_session,
            sample_client.id,
            voice_confidence_pct=85.0,
            gate_report={
                "gates": [
                    {"name": "length", "status": "passed"},
                    {"name": "readability", "status": "passed"},
                    {"name": "cliche", "status": "passed"},
                    {"name": "sensitivity", "status": "passed"},
                    {"name": "voice", "status": "passed"},
                ]
            },
        )
        obs = _make_observation(
            client_id=sample_client.id,
            approval_rate_30d=0.90,
        )
        config = _make_config(db_session, sample_client.id)

        judgment = evaluate_draft_confidence(db_session, draft, obs, config)

        assert judgment.auto_approve is True
        assert judgment.confidence_score > 0.8
        assert "Auto-approved" in judgment.rationale

    def test_judge_low_voice_confidence(self, db_session, sample_client):
        """Low voice confidence blocks auto-approval."""
        draft = _make_draft(
            db_session,
            sample_client.id,
            voice_confidence_pct=50.0,
        )
        obs = _make_observation(
            client_id=sample_client.id,
            approval_rate_30d=0.90,
        )
        config = _make_config(db_session, sample_client.id)

        judgment = evaluate_draft_confidence(db_session, draft, obs, config)

        assert judgment.auto_approve is False
        assert "voice confidence" in judgment.rationale.lower()

    def test_judge_failed_gate(self, db_session, sample_client):
        """Failed gate blocks auto-approval when require_all_gates_pass=True."""
        draft = _make_draft(
            db_session,
            sample_client.id,
            gate_report={
                "gates": [
                    {"name": "length", "status": "passed"},
                    {"name": "readability", "status": "passed"},
                    {"name": "cliche", "status": "failed"},
                    {"name": "sensitivity", "status": "passed"},
                    {"name": "voice", "status": "passed"},
                ]
            },
        )
        obs = _make_observation(
            client_id=sample_client.id,
            approval_rate_30d=0.90,
        )
        config = _make_config(
            db_session,
            sample_client.id,
            require_all_gates_pass=True,
        )

        judgment = evaluate_draft_confidence(db_session, draft, obs, config)

        assert judgment.auto_approve is False
        assert judgment.content_risk == "risky"  # failed gate = risky

    def test_judge_sensitive_content(self, db_session, sample_client):
        """Sensitivity gate flagging produces sensitive risk."""
        draft = _make_draft(
            db_session,
            sample_client.id,
            gate_report={
                "gates": [
                    {"name": "length", "status": "passed"},
                    {"name": "readability", "status": "passed"},
                    {"name": "cliche", "status": "passed"},
                    {"name": "sensitivity", "status": "flagged", "flagged": True},
                    {"name": "voice", "status": "passed"},
                ]
            },
        )
        obs = _make_observation(
            client_id=sample_client.id,
            approval_rate_30d=0.90,
        )
        config = _make_config(db_session, sample_client.id)

        judgment = evaluate_draft_confidence(db_session, draft, obs, config)

        assert judgment.content_risk == "sensitive"
        assert judgment.auto_approve is False

    def test_judge_low_approval_rate(self, db_session, sample_client):
        """Low historical approval rate blocks auto-approval."""
        draft = _make_draft(db_session, sample_client.id)
        obs = _make_observation(
            client_id=sample_client.id,
            approval_rate_30d=0.60,  # below 80% threshold
        )
        config = _make_config(db_session, sample_client.id)

        judgment = evaluate_draft_confidence(db_session, draft, obs, config)

        assert judgment.auto_approve is False
        assert "approval rate" in judgment.rationale.lower()

    def test_judge_rationale_lists_failures(self, db_session, sample_client):
        """Rationale mentions all failing signals when multiple fail."""
        draft = _make_draft(
            db_session,
            sample_client.id,
            voice_confidence_pct=50.0,  # below 75% threshold
        )
        obs = _make_observation(
            client_id=sample_client.id,
            approval_rate_30d=0.60,  # below 80% threshold
        )
        config = _make_config(db_session, sample_client.id)

        judgment = evaluate_draft_confidence(db_session, draft, obs, config)

        assert judgment.auto_approve is False
        rationale_lower = judgment.rationale.lower()
        assert "voice" in rationale_lower
        assert "approval rate" in rationale_lower


# ============================================================================
# Auto-Approval Tests
# ============================================================================


class TestAutoApproval:
    """Tests for should_auto_approve and related functions."""

    def test_burn_in_blocks_approval(self, db_session, sample_client):
        """Burn-in period prevents auto-approval."""
        _make_config(
            db_session,
            sample_client.id,
            burn_in_cycles=15,
            completed_cycles=5,
        )
        draft = _make_draft(db_session, sample_client.id)
        obs = _make_observation(
            client_id=sample_client.id,
            approval_rate_30d=0.90,
        )

        judgment = should_auto_approve(db_session, draft, obs)

        assert judgment.auto_approve is False
        assert "Burn-in period" in judgment.rationale
        assert "5/15" in judgment.rationale

    def test_past_burn_in_allows_evaluation(self, db_session, sample_client):
        """Past burn-in period allows normal evaluation."""
        _make_config(
            db_session,
            sample_client.id,
            completed_cycles=20,
            burn_in_cycles=15,
        )
        # Good draft with all signals passing
        draft = _make_draft(
            db_session,
            sample_client.id,
            voice_confidence_pct=85.0,
            gate_report={
                "gates": [
                    {"name": "length", "status": "passed"},
                    {"name": "readability", "status": "passed"},
                    {"name": "cliche", "status": "passed"},
                    {"name": "sensitivity", "status": "passed"},
                    {"name": "voice", "status": "passed"},
                ]
            },
        )
        obs = _make_observation(
            client_id=sample_client.id,
            approval_rate_30d=0.90,
        )

        judgment = should_auto_approve(db_session, draft, obs)

        assert judgment.auto_approve is True
        assert "Auto-approved" in judgment.rationale

    def test_suspension_on_false_positives(self, db_session, sample_client):
        """3+ false positives in 7 days suspends auto-approval."""
        _make_config(
            db_session,
            sample_client.id,
            completed_cycles=20,
            burn_in_cycles=15,
        )
        # Create specialist with 3 false positives in current window
        _make_specialist(
            db_session,
            sample_client.id,
            false_positive_count=3,
            false_positive_window_start=_now_naive() - timedelta(days=1),
        )

        draft = _make_draft(db_session, sample_client.id)
        obs = _make_observation(
            client_id=sample_client.id,
            approval_rate_30d=0.90,
        )

        judgment = should_auto_approve(db_session, draft, obs)

        assert judgment.auto_approve is False
        assert "suspended" in judgment.rationale.lower()

    def test_disabled_config(self, db_session, sample_client):
        """Disabled auto-approval config returns disabled rationale."""
        _make_config(
            db_session,
            sample_client.id,
            enabled=False,
        )
        draft = _make_draft(db_session, sample_client.id)
        obs = _make_observation(
            client_id=sample_client.id,
            approval_rate_30d=0.90,
        )

        judgment = should_auto_approve(db_session, draft, obs)

        assert judgment.auto_approve is False
        assert "disabled" in judgment.rationale.lower()

    def test_signals_dict_in_judgment(self, db_session, sample_client):
        """DraftJudgment.signals dict contains all 4 signal values."""
        _make_config(
            db_session,
            sample_client.id,
            completed_cycles=20,
            burn_in_cycles=15,
        )
        draft = _make_draft(db_session, sample_client.id)
        obs = _make_observation(
            client_id=sample_client.id,
            approval_rate_30d=0.90,
        )

        judgment = should_auto_approve(db_session, draft, obs)

        # When past pre-checks, signals should contain all 4 signal values
        assert "voice_confidence" in judgment.signals
        assert "gate_pass_rate" in judgment.signals
        assert "content_risk" in judgment.signals
        assert "historical_approval_rate" in judgment.signals
