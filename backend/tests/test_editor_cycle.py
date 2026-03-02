"""Integration tests for the Editor Agent daily cycle orchestrator.

Covers:
- Full cycle execution with audit trail (CycleRun + CycleStage records)
- Stage decision traces contain stage-specific data
- Auto-approval of high-confidence content
- Flagging of low-confidence content
- Graceful stage timeout handling (cycle marked partial)
- Specialist agent state updates after cycle
- Exception briefing generation
- API endpoints: manual trigger and cycle list
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sophia.content.models import ContentDraft
from sophia.orchestrator.auto_approval import should_auto_approve
from sophia.orchestrator.editor import (
    generate_exception_briefing,
    run_daily_cycle,
)
from sophia.orchestrator.models import (
    AutoApprovalConfig,
    CycleRun,
    CycleStage,
    SpecialistAgent,
)
from sophia.orchestrator.observer import ClientObservation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_naive():
    """Current UTC time as naive datetime (SQLite pattern)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _make_observation(client_id=1, **overrides):
    """Create a ClientObservation with defaults for testing."""
    defaults = {
        "client_id": client_id,
        "client_name": "Test Client",
        "last_post_date": None,
        "days_since_last_post": 9999,
        "pending_approvals": 0,
        "recent_engagement_trend": "stable",
        "research_freshness_hours": 10.0,
        "needs_research": False,
        "active_anomalies": 0,
        "approval_rate_30d": 0.90,
        "completed_cycles": 20,
    }
    defaults.update(overrides)
    return ClientObservation(**defaults)


def _make_draft_mock(draft_id, client_id, voice_pct=85.0, gates_pass=True):
    """Create a mock ContentDraft for testing."""
    draft = MagicMock(spec=ContentDraft)
    draft.id = draft_id
    draft.client_id = client_id
    draft.voice_confidence_pct = voice_pct
    draft.status = "pending_review"
    draft.cycle_id = None
    if gates_pass:
        draft.gate_report = {
            "gates": [
                {"name": "length", "status": "passed"},
                {"name": "readability", "status": "passed"},
                {"name": "cliche", "status": "passed"},
                {"name": "sensitivity", "status": "passed"},
                {"name": "voice", "status": "passed"},
            ]
        }
    else:
        draft.gate_report = {
            "gates": [
                {"name": "length", "status": "passed"},
                {"name": "readability", "status": "failed"},
            ]
        }
    return draft


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


def _make_real_draft(db, client_id, **overrides):
    """Create a real ContentDraft in the database.

    Uses status='draft' to match what generate_content_batch produces.
    The editor agent transitions draft -> in_review -> approved.
    """
    defaults = {
        "client_id": client_id,
        "platform": "facebook",
        "content_type": "feed",
        "copy": "Test post content",
        "image_prompt": "A photo of a test",
        "image_ratio": "1:1",
        "status": "draft",
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


# ============================================================================
# Cycle Execution Tests
# ============================================================================


class TestEditorCycle:
    """Tests for the daily cycle orchestrator."""

    def test_run_cycle_creates_run_and_stages(self, db_session, sample_client):
        """Full cycle creates CycleRun and CycleStage records."""
        # Setup: config and specialist
        _make_config(db_session, sample_client.id)
        _make_specialist(db_session, sample_client.id)

        observation = _make_observation(
            client_id=sample_client.id,
            client_name=sample_client.name,
            needs_research=False,
        )

        drafts = [
            _make_real_draft(db_session, sample_client.id, copy=f"Draft {i}")
            for i in range(2)
        ]

        with patch(
            "sophia.orchestrator.editor.asyncio.to_thread"
        ) as mock_to_thread:
            # Set up to_thread to dispatch correctly
            async def _mock_to_thread(func, *args, **kwargs):
                if func.__module__ and "observer" in func.__module__:
                    return observation
                elif func.__module__ and "content" in func.__module__:
                    return drafts
                return func(*args, **kwargs)

            mock_to_thread.side_effect = _mock_to_thread

            with patch(
                "sophia.orchestrator.observer.observe_client_state",
                return_value=observation,
            ), patch(
                "sophia.content.service.generate_content_batch",
                return_value=drafts,
            ), patch(
                "sophia.agent.learning.persist_learning",
            ) as mock_learn:
                mock_learn.return_value = MagicMock(id=1)

                cycle = asyncio.get_event_loop().run_until_complete(
                    run_daily_cycle(db_session, sample_client.id)
                )

        assert cycle is not None
        assert isinstance(cycle, CycleRun)
        assert cycle.client_id == sample_client.id
        assert cycle.status in ("completed", "partial")

        # Check stages were created
        stages = (
            db_session.query(CycleStage)
            .filter(CycleStage.cycle_run_id == cycle.id)
            .all()
        )
        stage_names = {s.stage_name for s in stages}
        # At minimum: observe, research (skipped), generate, judge, learn
        assert "observe" in stage_names
        assert len(stages) >= 3  # at least observe + generate + learn (or judge)

    def test_cycle_stage_decision_traces(self, db_session, sample_client):
        """CycleStage records have non-null decision_trace JSON."""
        _make_config(db_session, sample_client.id)
        _make_specialist(db_session, sample_client.id)

        observation = _make_observation(
            client_id=sample_client.id,
            client_name=sample_client.name,
            needs_research=False,
        )

        drafts = [_make_real_draft(db_session, sample_client.id)]

        with patch(
            "sophia.orchestrator.observer.observe_client_state",
            return_value=observation,
        ), patch(
            "sophia.content.service.generate_content_batch",
            return_value=drafts,
        ), patch(
            "sophia.agent.learning.persist_learning",
        ) as mock_learn:
            mock_learn.return_value = MagicMock(id=1)

            cycle = asyncio.get_event_loop().run_until_complete(
                run_daily_cycle(db_session, sample_client.id)
            )

        stages = (
            db_session.query(CycleStage)
            .filter(
                CycleStage.cycle_run_id == cycle.id,
                CycleStage.status.in_(["completed", "skipped"]),
            )
            .all()
        )

        for stage in stages:
            assert stage.decision_trace is not None, (
                f"Stage {stage.stage_name} has null decision_trace"
            )

    def test_cycle_auto_approves_high_confidence(self, db_session, sample_client):
        """High-confidence drafts are auto-approved during the cycle."""
        _make_config(
            db_session,
            sample_client.id,
            enabled=True,
            completed_cycles=20,
            burn_in_cycles=15,
        )
        _make_specialist(db_session, sample_client.id)

        observation = _make_observation(
            client_id=sample_client.id,
            client_name=sample_client.name,
            needs_research=False,
            approval_rate_30d=0.90,
        )

        # Create drafts with high voice confidence + all gates passing
        drafts = [
            _make_real_draft(
                db_session,
                sample_client.id,
                copy=f"High quality draft {i}",
                voice_confidence_pct=85.0,
            )
            for i in range(2)
        ]

        with patch(
            "sophia.orchestrator.observer.observe_client_state",
            return_value=observation,
        ), patch(
            "sophia.content.service.generate_content_batch",
            return_value=drafts,
        ), patch(
            "sophia.agent.learning.persist_learning",
        ) as mock_learn:
            mock_learn.return_value = MagicMock(id=1)

            cycle = asyncio.get_event_loop().run_until_complete(
                run_daily_cycle(db_session, sample_client.id)
            )

        assert cycle.drafts_auto_approved == 2
        assert cycle.drafts_flagged == 0

    def test_cycle_flags_low_confidence(self, db_session, sample_client):
        """Low-confidence drafts are flagged for review, not auto-approved."""
        _make_config(
            db_session,
            sample_client.id,
            enabled=True,
            completed_cycles=20,
            burn_in_cycles=15,
        )
        _make_specialist(db_session, sample_client.id)

        observation = _make_observation(
            client_id=sample_client.id,
            client_name=sample_client.name,
            needs_research=False,
            approval_rate_30d=0.90,
        )

        # Create draft with LOW voice confidence
        drafts = [
            _make_real_draft(
                db_session,
                sample_client.id,
                copy="Low confidence draft",
                voice_confidence_pct=40.0,
            )
        ]

        with patch(
            "sophia.orchestrator.observer.observe_client_state",
            return_value=observation,
        ), patch(
            "sophia.content.service.generate_content_batch",
            return_value=drafts,
        ), patch(
            "sophia.agent.learning.persist_learning",
        ) as mock_learn:
            mock_learn.return_value = MagicMock(id=1)

            cycle = asyncio.get_event_loop().run_until_complete(
                run_daily_cycle(db_session, sample_client.id)
            )

        assert cycle.drafts_auto_approved == 0
        assert cycle.drafts_flagged == 1

    def test_cycle_stage_timeout_marks_partial(self, db_session, sample_client):
        """When a stage times out, cycle status is 'partial' but continues."""
        _make_config(db_session, sample_client.id)
        _make_specialist(db_session, sample_client.id)

        observation = _make_observation(
            client_id=sample_client.id,
            client_name=sample_client.name,
            needs_research=False,
        )

        with patch(
            "sophia.orchestrator.observer.observe_client_state",
            return_value=observation,
        ), patch(
            "sophia.content.service.generate_content_batch",
            side_effect=asyncio.TimeoutError("Simulated timeout"),
        ), patch(
            "sophia.agent.learning.persist_learning",
        ) as mock_learn:
            mock_learn.return_value = MagicMock(id=1)

            cycle = asyncio.get_event_loop().run_until_complete(
                run_daily_cycle(db_session, sample_client.id)
            )

        assert cycle.status == "partial"

        # Check generate stage is marked as failed
        generate_stage = (
            db_session.query(CycleStage)
            .filter(
                CycleStage.cycle_run_id == cycle.id,
                CycleStage.stage_name == "generate",
            )
            .first()
        )
        assert generate_stage is not None
        assert generate_stage.status == "failed"

        # Learn stage should still have been attempted
        learn_stage = (
            db_session.query(CycleStage)
            .filter(
                CycleStage.cycle_run_id == cycle.id,
                CycleStage.stage_name == "learn",
            )
            .first()
        )
        assert learn_stage is not None

    def test_cycle_specialist_state_updated(self, db_session, sample_client):
        """Specialist agent's total_cycles and last_cycle_id are updated."""
        _make_config(db_session, sample_client.id)
        specialist = _make_specialist(db_session, sample_client.id, total_cycles=5)
        initial_cycles = specialist.total_cycles

        observation = _make_observation(
            client_id=sample_client.id,
            client_name=sample_client.name,
            needs_research=False,
        )

        drafts = [_make_real_draft(db_session, sample_client.id)]

        with patch(
            "sophia.orchestrator.observer.observe_client_state",
            return_value=observation,
        ), patch(
            "sophia.content.service.generate_content_batch",
            return_value=drafts,
        ), patch(
            "sophia.agent.learning.persist_learning",
        ) as mock_learn:
            mock_learn.return_value = MagicMock(id=1)

            cycle = asyncio.get_event_loop().run_until_complete(
                run_daily_cycle(db_session, sample_client.id)
            )

        # Refresh specialist from DB
        db_session.expire(specialist)
        assert specialist.total_cycles == initial_cycles + 1
        assert specialist.last_cycle_id == cycle.id

    def test_exception_briefing_generated(
        self, db_session, sample_client, sample_client_2
    ):
        """Exception briefing aggregates results from multiple client cycles."""
        cycle_results = [
            {
                "client_id": sample_client.id,
                "client_name": sample_client.name,
                "cycle_id": 1,
                "status": "completed",
                "auto_approved": 2,
                "flagged": 1,
                "drafts_generated": 3,
            },
            {
                "client_id": sample_client_2.id,
                "client_name": sample_client_2.name,
                "cycle_id": 2,
                "status": "completed",
                "auto_approved": 3,
                "flagged": 0,
                "drafts_generated": 3,
            },
        ]

        briefing = asyncio.get_event_loop().run_until_complete(
            generate_exception_briefing(db_session, cycle_results)
        )

        assert briefing["summary"]["total_auto_approved"] == 5
        assert briefing["summary"]["total_flagged"] == 1
        assert briefing["summary"]["total_failures"] == 0
        assert briefing["summary"]["total_clients"] == 2

    def test_manual_trigger_endpoint(self, db_session, sample_client):
        """POST /api/orchestrator/cycle/{client_id} returns 200."""
        from fastapi.testclient import TestClient

        from sophia.orchestrator.router import orchestrator_router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(orchestrator_router)

        # Override DB dependency
        def override_get_db():
            try:
                yield db_session
            finally:
                pass

        from sophia.orchestrator.router import _get_db

        app.dependency_overrides[_get_db] = override_get_db

        client = TestClient(app)
        response = client.post(f"/api/orchestrator/cycle/{sample_client.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["client_id"] == sample_client.id
        assert data["status"] == "pending"

    def test_cycle_list_endpoint(self, db_session, sample_client):
        """GET /api/orchestrator/cycles/{client_id} returns cycle history."""
        # Create 3 CycleRun records
        for i in range(3):
            cycle = CycleRun(
                client_id=sample_client.id,
                status="completed",
                started_at=_now_naive(),
                completed_at=_now_naive(),
                drafts_generated=2,
                drafts_auto_approved=1,
                drafts_flagged=1,
            )
            db_session.add(cycle)
        db_session.flush()

        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        from sophia.orchestrator.router import orchestrator_router, _get_db

        app = FastAPI()
        app.include_router(orchestrator_router)

        def override_get_db():
            try:
                yield db_session
            finally:
                pass

        app.dependency_overrides[_get_db] = override_get_db

        client = TestClient(app)
        response = client.get(f"/api/orchestrator/cycles/{sample_client.id}")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        # Should be ordered by most recent (desc)
        assert all(d["client_id"] == sample_client.id for d in data)
