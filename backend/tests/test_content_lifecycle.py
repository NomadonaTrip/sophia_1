"""Tests for content lifecycle: regeneration, format adaptation, AI labeling,
evergreen bank management, voice calibration sessions, and content API router.

All external dependencies (quality gates, research, intelligence) are mocked.
Tests validate service logic and orchestration, not the LLM itself.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sophia.content.ai_label import (
    AI_LABEL_RULES,
    apply_ai_label,
    get_label_requirements_summary,
    should_apply_ai_label,
)
from sophia.content.models import (
    CalibrationRound,
    CalibrationSession,
    ContentDraft,
    EvergreenEntry,
    FormatPerformance,
    RegenerationLog,
)
from sophia.content.router import content_router, _get_db
from sophia.content.service import (
    _analyze_guidance_patterns,
    analyze_rejection_patterns,
    calibrate_ranking_from_choices,
    create_calibration_session,
    explain_format_adaptations,
    finalize_calibration,
    generate_calibration_round,
    get_evergreen_options,
    get_format_weights,
    manage_evergreen_bank,
    mark_evergreen_used,
    record_calibration_choice,
    regenerate_draft,
    suggest_voice_profile_updates,
    update_format_performance,
)
from sophia.exceptions import ContentGenerationError, RegenerationLimitError


# =============================================================================
# Helpers
# =============================================================================


def _make_draft(
    db_session,
    client_id: int,
    copy: str = "Original draft content for testing.",
    status: str = "draft",
    regeneration_count: int = 0,
    **kwargs,
) -> ContentDraft:
    """Create and persist a ContentDraft."""
    defaults = dict(
        client_id=client_id,
        platform="instagram",
        content_type="feed",
        copy=copy,
        image_prompt="Test image prompt",
        image_ratio="1:1",
        status=status,
        regeneration_count=regeneration_count,
        gate_status="passed",
    )
    defaults.update(kwargs)
    draft = ContentDraft(**defaults)
    db_session.add(draft)
    db_session.flush()
    return draft


def _make_evergreen(db_session, client_id: int, draft_id: int, **kwargs) -> EvergreenEntry:
    """Create and persist an EvergreenEntry."""
    defaults = dict(
        client_id=client_id,
        content_draft_id=draft_id,
        platform="instagram",
        content_type="feed",
        is_used=False,
    )
    defaults.update(kwargs)
    entry = EvergreenEntry(**defaults)
    db_session.add(entry)
    db_session.flush()
    return entry


# =============================================================================
# Regeneration Tests
# =============================================================================


class TestRegenerateDraft:
    """Tests for the regeneration service."""

    @patch("sophia.content.service._validate_voice_profile")
    @patch("sophia.content.service._validate_intelligence")
    @patch("sophia.content.service._validate_research")
    @patch("sophia.content.service.run_quality_gates")
    def test_regenerate_with_valid_guidance(
        self, mock_gates, mock_research, mock_intel, mock_voice,
        db_session, sample_client
    ):
        """Regeneration with valid guidance increments count and appends guidance."""
        draft = _make_draft(db_session, sample_client.id)
        mock_research.return_value = [{"topic": "Test"}]
        mock_intel.return_value = MagicMock()
        mock_voice.return_value = {"base_voice": {}}

        from sophia.content.quality_gates import QualityReport
        mock_gates.return_value = QualityReport(
            status="passed", results=[], summary_badge="Passed"
        )

        result = regenerate_draft(db_session, draft.id, "Make it funnier and shorter")

        assert result.regeneration_count == 1
        assert "Make it funnier and shorter" in result.regeneration_guidance
        assert "[Regenerated with guidance:" in result.copy

    @patch("sophia.content.service._validate_voice_profile")
    @patch("sophia.content.service._validate_intelligence")
    @patch("sophia.content.service._validate_research")
    @patch("sophia.content.service.run_quality_gates")
    def test_regenerate_at_limit_raises_error(
        self, mock_gates, mock_research, mock_intel, mock_voice,
        db_session, sample_client
    ):
        """Regeneration at count=3 raises RegenerationLimitError."""
        draft = _make_draft(
            db_session, sample_client.id, regeneration_count=3
        )

        with pytest.raises(RegenerationLimitError) as exc_info:
            regenerate_draft(db_session, draft.id, "More casual please")

        assert "3-attempt limit" in str(exc_info.value)

    @patch("sophia.content.service._validate_voice_profile")
    @patch("sophia.content.service._validate_intelligence")
    @patch("sophia.content.service._validate_research")
    @patch("sophia.content.service.run_quality_gates")
    def test_regenerate_runs_quality_gates(
        self, mock_gates, mock_research, mock_intel, mock_voice,
        db_session, sample_client
    ):
        """Regenerated content goes through full quality gate pipeline."""
        draft = _make_draft(db_session, sample_client.id)
        mock_research.return_value = [{"topic": "Test"}]
        mock_intel.return_value = MagicMock()
        mock_voice.return_value = {"base_voice": {}}

        from sophia.content.quality_gates import QualityReport
        mock_gates.return_value = QualityReport(
            status="passed", results=[], summary_badge="Passed"
        )

        regenerate_draft(db_session, draft.id, "Better hook")

        # Verify run_quality_gates was called (no shortcuts)
        mock_gates.assert_called_once()

    @patch("sophia.content.service._validate_voice_profile")
    @patch("sophia.content.service._validate_intelligence")
    @patch("sophia.content.service._validate_research")
    def test_regenerate_validates_three_inputs(
        self, mock_research, mock_intel, mock_voice,
        db_session, sample_client
    ):
        """Regeneration re-validates three mandatory inputs."""
        draft = _make_draft(db_session, sample_client.id)
        mock_research.side_effect = ContentGenerationError(
            message="No research",
            reason="missing_research",
        )

        with pytest.raises(ContentGenerationError) as exc_info:
            regenerate_draft(db_session, draft.id, "Some guidance")

        assert "research" in str(exc_info.value).lower()


class TestAnalyzeGuidancePatterns:
    """Tests for guidance pattern detection."""

    def test_detects_pattern_at_threshold(self, db_session, sample_client):
        """7 similar guidance strings should detect humor pattern."""
        draft = _make_draft(db_session, sample_client.id)

        # Create 7 humor-related guidance entries
        humor_phrases = [
            "Make it funnier",
            "More humor please",
            "Can you add some jokes",
            "Lighter tone, more funny",
            "This needs to be funnier",
            "Add some humor to it",
            "Make it more humorous and witty",
        ]
        for i, phrase in enumerate(humor_phrases):
            log = RegenerationLog(
                content_draft_id=draft.id,
                client_id=sample_client.id,
                attempt_number=i + 1,
                guidance=phrase,
            )
            db_session.add(log)
        db_session.flush()

        patterns = _analyze_guidance_patterns(db_session, sample_client.id)

        assert len(patterns) >= 1
        humor_pattern = next(
            (p for p in patterns if "humor" in p["pattern"].lower()),
            None,
        )
        assert humor_pattern is not None
        assert humor_pattern["count"] >= 5
        assert "humor" in humor_pattern["suggestion"].lower() or "voice profile" in humor_pattern["suggestion"].lower()

    def test_no_patterns_for_diverse_guidance(self, db_session, sample_client):
        """Diverse guidance should not flag any patterns."""
        draft = _make_draft(db_session, sample_client.id)

        diverse_phrases = [
            "Change the opening line",
            "Remove the second paragraph",
            "Add a hashtag",
            "Different image description",
        ]
        for i, phrase in enumerate(diverse_phrases):
            log = RegenerationLog(
                content_draft_id=draft.id,
                client_id=sample_client.id,
                attempt_number=i + 1,
                guidance=phrase,
            )
            db_session.add(log)
        db_session.flush()

        patterns = _analyze_guidance_patterns(db_session, sample_client.id)
        assert len(patterns) == 0


class TestSuggestVoiceProfileUpdates:
    """Tests for voice profile update suggestions."""

    def test_formats_suggestions_correctly(self, db_session, sample_client):
        """Suggestions should be formatted for operator readability."""
        draft = _make_draft(db_session, sample_client.id)

        # Create enough humor guidance to trigger pattern
        for i in range(6):
            log = RegenerationLog(
                content_draft_id=draft.id,
                client_id=sample_client.id,
                attempt_number=i + 1,
                guidance=f"Make it funnier version {i}",
            )
            db_session.add(log)
        db_session.flush()

        suggestions = suggest_voice_profile_updates(db_session, sample_client.id)

        assert len(suggestions) >= 1
        assert any("humor" in s.lower() for s in suggestions)
        assert any("regeneration requests" in s.lower() for s in suggestions)


# =============================================================================
# Format Adaptation Tests
# =============================================================================


class TestGetFormatWeights:
    """Tests for performance-weighted format selection."""

    def test_weights_with_performance_data(self, db_session, sample_client):
        """Higher-performing formats should get higher weight."""
        # Create performance data: question format performs 2x average
        perf_q = FormatPerformance(
            client_id=sample_client.id,
            platform="instagram",
            content_format="question",
            sample_count=10,
            avg_engagement_rate=0.08,
        )
        perf_h = FormatPerformance(
            client_id=sample_client.id,
            platform="instagram",
            content_format="how-to",
            sample_count=10,
            avg_engagement_rate=0.02,
        )
        db_session.add_all([perf_q, perf_h])
        db_session.flush()

        weights = get_format_weights(db_session, sample_client.id, "instagram")

        assert weights["question"] > weights["how-to"]
        # Untested formats should get exploration weight
        assert weights.get("listicle", 0) > 0

    def test_weights_no_data_equal(self, db_session, sample_client):
        """New client with no data should get equal weights."""
        weights = get_format_weights(db_session, sample_client.id, "instagram")

        values = list(weights.values())
        assert len(values) > 0
        # All weights should be approximately equal
        avg = sum(values) / len(values)
        for v in values:
            assert abs(v - avg) < 0.01


class TestUpdateFormatPerformance:
    """Tests for format performance tracking."""

    def test_creates_new_record(self, db_session, sample_client):
        """First observation creates a new record."""
        result = update_format_performance(
            db_session, sample_client.id, "instagram", "question",
            engagement_rate=0.05, save_rate=0.01, ctr=0.03,
        )

        assert result.sample_count == 1
        assert result.avg_engagement_rate == 0.05
        assert result.avg_save_rate == 0.01
        assert result.avg_ctr == 0.03

    def test_updates_with_ema(self, db_session, sample_client):
        """Second observation uses EMA (alpha=0.3)."""
        update_format_performance(
            db_session, sample_client.id, "instagram", "question",
            engagement_rate=0.10,
        )
        result = update_format_performance(
            db_session, sample_client.id, "instagram", "question",
            engagement_rate=0.05,
        )

        assert result.sample_count == 2
        # EMA: 0.3 * 0.05 + 0.7 * 0.10 = 0.085
        assert abs(result.avg_engagement_rate - 0.085) < 0.001


class TestExplainFormatAdaptations:
    """Tests for natural language format explanations."""

    def test_explains_significant_shifts(self, db_session, sample_client):
        """Significant weight shifts should produce explanations."""
        # Create one high-performing format
        perf = FormatPerformance(
            client_id=sample_client.id,
            platform="instagram",
            content_format="question",
            sample_count=20,
            avg_engagement_rate=0.15,
        )
        # And one low-performing
        perf2 = FormatPerformance(
            client_id=sample_client.id,
            platform="instagram",
            content_format="promotional",
            sample_count=20,
            avg_engagement_rate=0.01,
        )
        db_session.add_all([perf, perf2])
        db_session.flush()

        explanations = explain_format_adaptations(db_session, sample_client.id)

        assert len(explanations) > 0
        assert any("question" in e.lower() for e in explanations)


class TestAnalyzeRejectionPatterns:
    """Tests for rejection pattern detection."""

    def test_flags_high_rejection_rate(self, db_session, sample_client):
        """Categories with >80% rejection should be flagged."""
        # Create 6 promotional feed drafts, 5 rejected by operator (83%)
        for i in range(6):
            _make_draft(
                db_session,
                sample_client.id,
                copy=f"Promotional draft {i}",
                status="rejected" if i < 5 else "approved",
                content_pillar="promotional",
                content_format="feed",
            )

        result = analyze_rejection_patterns(db_session, sample_client.id)

        assert "promotional_feed" in result
        assert result["promotional_feed"]["rejection_rate"] > 0.80


class TestCalibrateRankingFromChoices:
    """Tests for ranking calibration."""

    def test_detects_non_first_preference(self, db_session, sample_client):
        """Detects when operator consistently picks non-#1 ranked drafts."""
        # Create approved drafts: most picked rank #2
        for i in range(6):
            _make_draft(
                db_session,
                sample_client.id,
                copy=f"Approved {i}",
                status="approved",
                rank=2 if i < 4 else 1,
            )

        result = calibrate_ranking_from_choices(db_session, sample_client.id)

        assert result["total_approved"] == 6
        assert result["signal"] is not None
        assert "rank #2" in result["signal"]


# =============================================================================
# AI Labeling Tests
# =============================================================================


class TestShouldApplyAiLabel:
    """Tests for AI labeling decision logic."""

    def test_text_only_facebook_no_label(self):
        """Text-only Facebook post does NOT require AI label."""
        assert should_apply_ai_label("facebook", "feed", has_ai_image=False) is False

    def test_text_only_instagram_no_label(self):
        """Text-only Instagram post does NOT require AI label."""
        assert should_apply_ai_label("instagram", "feed", has_ai_image=False) is False

    def test_ai_image_instagram_requires_label(self):
        """Instagram post with AI image DOES require AI label."""
        assert should_apply_ai_label("instagram", "feed", has_ai_image=True) is True

    def test_ai_image_facebook_requires_label(self):
        """Facebook post with AI image DOES require AI label."""
        assert should_apply_ai_label("facebook", "feed", has_ai_image=True) is True

    def test_unknown_platform_defaults_to_label(self):
        """Unknown platform defaults to requiring label (safety)."""
        assert should_apply_ai_label("tiktok", "feed", has_ai_image=False) is True


class TestApplyAiLabel:
    """Tests for AI label application."""

    def test_sets_has_ai_label(self, db_session, sample_client):
        """apply_ai_label sets has_ai_label=True on draft."""
        draft = _make_draft(db_session, sample_client.id)
        assert draft.has_ai_label is False

        result = apply_ai_label(draft)

        assert result.has_ai_label is True
        assert result is draft  # Same object returned


class TestGetLabelRequirementsSummary:
    """Tests for label requirements summary."""

    def test_returns_per_platform_summary(self):
        """Summary should cover each platform in AI_LABEL_RULES."""
        summary = get_label_requirements_summary()

        assert "facebook" in summary
        assert "instagram" in summary

        fb = summary["facebook"]
        assert fb["text_only_required"] is False
        assert fb["photorealistic_image_required"] is True
        assert "description" in fb
        assert "Not required" in fb["description"]


# =============================================================================
# Evergreen Bank Tests
# =============================================================================


class TestManageEvergreenBank:
    """Tests for evergreen bank management."""

    def test_respects_cap(self, db_session, sample_client):
        """Entries exceeding 20-entry cap should be expired."""
        # Create 25 evergreen entries
        for i in range(25):
            draft = _make_draft(
                db_session, sample_client.id, copy=f"Evergreen {i}"
            )
            _make_evergreen(db_session, sample_client.id, draft.id)

        result = manage_evergreen_bank(db_session, sample_client.id)

        assert result["capped_count"] == 5
        assert result["active_count"] == 20

    def test_expires_old_entries(self, db_session, sample_client):
        """Entries older than 90 days should be expired."""
        draft = _make_draft(db_session, sample_client.id)
        entry = _make_evergreen(db_session, sample_client.id, draft.id)

        # Manually set created_at to 91 days ago
        old_date = datetime.now(timezone.utc) - timedelta(days=91)
        db_session.execute(
            EvergreenEntry.__table__.update()
            .where(EvergreenEntry.id == entry.id)
            .values(created_at=old_date)
        )
        db_session.flush()

        result = manage_evergreen_bank(db_session, sample_client.id)

        assert result["expired_count"] == 1


class TestGetEvergreenOptions:
    """Tests for retrieving unused evergreen entries."""

    def test_returns_unused_within_window(self, db_session, sample_client):
        """Should return unused entries within 90-day window."""
        draft = _make_draft(db_session, sample_client.id)
        entry = _make_evergreen(db_session, sample_client.id, draft.id)

        options = get_evergreen_options(db_session, sample_client.id)

        assert len(options) == 1
        assert options[0].id == entry.id
        assert options[0].is_used is False

    def test_excludes_used_entries(self, db_session, sample_client):
        """Used entries should not be returned."""
        draft = _make_draft(db_session, sample_client.id)
        entry = _make_evergreen(db_session, sample_client.id, draft.id)
        entry.is_used = True
        db_session.flush()

        options = get_evergreen_options(db_session, sample_client.id)

        assert len(options) == 0


class TestMarkEvergreenUsed:
    """Tests for marking evergreen entries as used."""

    def test_marks_used(self, db_session, sample_client):
        """Should set is_used=True and used_at."""
        draft = _make_draft(db_session, sample_client.id)
        entry = _make_evergreen(db_session, sample_client.id, draft.id)

        result = mark_evergreen_used(db_session, entry.id)

        assert result.is_used is True
        assert result.used_at is not None


# =============================================================================
# Voice Calibration Tests (CONT-09)
# =============================================================================


class TestCreateCalibrationSession:
    """Tests for calibration session creation."""

    def test_creates_session(self, db_session, sample_client):
        """Session created with correct total_rounds and status."""
        session = create_calibration_session(db_session, sample_client.id, total_rounds=8)

        assert session.id is not None
        assert session.client_id == sample_client.id
        assert session.total_rounds == 8
        assert session.rounds_completed == 0
        assert session.status == "in_progress"

    def test_clamps_rounds_to_range(self, db_session, sample_client):
        """total_rounds is clamped to 5-10 range."""
        session = create_calibration_session(db_session, sample_client.id, total_rounds=3)
        assert session.total_rounds == 5

        session2 = create_calibration_session(db_session, sample_client.id, total_rounds=15)
        assert session2.total_rounds == 10


class TestGenerateCalibrationRound:
    """Tests for A/B comparison round generation."""

    def test_generates_two_options(self, db_session, sample_client):
        """Round should have two different text options."""
        session = create_calibration_session(db_session, sample_client.id)
        cal_round = generate_calibration_round(db_session, session.id)

        assert cal_round.id is not None
        assert cal_round.round_number == 1
        assert cal_round.option_a != cal_round.option_b
        assert len(cal_round.option_a) > 0
        assert len(cal_round.option_b) > 0


class TestRecordCalibrationChoice:
    """Tests for recording operator choices."""

    def test_records_choice_a(self, db_session, sample_client):
        """Selecting 'a' records voice_delta and increments rounds."""
        session = create_calibration_session(db_session, sample_client.id, total_rounds=5)
        cal_round = generate_calibration_round(db_session, session.id)

        result = record_calibration_choice(db_session, cal_round.id, "a")

        assert result.selected == "a"
        assert result.voice_delta is not None
        assert "brevity_preference" in result.voice_delta

        # Session progress incremented
        db_session.refresh(session)
        assert session.rounds_completed == 1

    def test_final_round_completes_session(self, db_session, sample_client):
        """Completing all rounds sets session status to 'completed'."""
        session = create_calibration_session(db_session, sample_client.id, total_rounds=5)

        for i in range(5):
            cal_round = generate_calibration_round(db_session, session.id)
            record_calibration_choice(db_session, cal_round.id, "a" if i % 2 == 0 else "b")

        db_session.refresh(session)
        assert session.status == "completed"
        assert session.rounds_completed == 5


class TestFinalizeCalibration:
    """Tests for calibration finalization."""

    def test_aggregates_deltas(self, db_session, sample_client):
        """Finalization aggregates voice deltas and produces summary."""
        session = create_calibration_session(db_session, sample_client.id, total_rounds=5)

        # Complete all rounds (all pick 'a' -- prefer brevity)
        for _ in range(5):
            cal_round = generate_calibration_round(db_session, session.id)
            record_calibration_choice(db_session, cal_round.id, "a")

        result = finalize_calibration(db_session, session.id)

        assert result["session_id"] == session.id
        assert result["rounds_completed"] == 5
        assert result["adjustments"]["brevity_preference"] > 0
        assert "shorter" in result["summary"].lower() or "punchi" in result["summary"].lower()

    def test_per_client_only(self, db_session, sample_client, sample_client_2):
        """Calibration sessions are per-client only."""
        session1 = create_calibration_session(db_session, sample_client.id)
        session2 = create_calibration_session(db_session, sample_client_2.id)

        assert session1.client_id == sample_client.id
        assert session2.client_id == sample_client_2.id
        assert session1.id != session2.id


# =============================================================================
# Router Tests (using TestClient)
# =============================================================================


@pytest.fixture
def test_app(db_session):
    """Create a FastAPI test app with DB dependency override."""
    app = FastAPI()
    app.include_router(content_router)

    def override_get_db():
        return db_session

    app.dependency_overrides[_get_db] = override_get_db
    return app


@pytest.fixture
def client(test_app):
    """Create a TestClient for the content router."""
    return TestClient(test_app)


class TestRouterDraftEndpoints:
    """Tests for content draft API endpoints."""

    def test_list_drafts(self, client, db_session, sample_client):
        """GET /api/content/drafts returns list."""
        _make_draft(db_session, sample_client.id, copy="Test draft 1")
        _make_draft(db_session, sample_client.id, copy="Test draft 2")

        response = client.get(f"/api/content/drafts?client_id={sample_client.id}")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_get_latest_batch(self, client, db_session, sample_client):
        """GET /api/content/batch/{id}/latest returns ranked batch."""
        _make_draft(db_session, sample_client.id, copy="Draft 1", rank=2)
        _make_draft(db_session, sample_client.id, copy="Draft 2", rank=1)

        response = client.get(f"/api/content/batch/{sample_client.id}/latest")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        # Should be sorted by rank
        assert data[0]["rank"] == 1


class TestRouterRegenerationEndpoints:
    """Tests for regeneration API endpoints."""

    @patch("sophia.content.service._validate_voice_profile")
    @patch("sophia.content.service._validate_intelligence")
    @patch("sophia.content.service._validate_research")
    @patch("sophia.content.service.run_quality_gates")
    def test_regenerate_endpoint(
        self, mock_gates, mock_research, mock_intel, mock_voice,
        client, db_session, sample_client
    ):
        """POST /api/content/drafts/{id}/regenerate returns updated draft."""
        draft = _make_draft(db_session, sample_client.id)
        mock_research.return_value = [{"topic": "Test"}]
        mock_intel.return_value = MagicMock()
        mock_voice.return_value = {"base_voice": {}}

        from sophia.content.quality_gates import QualityReport
        mock_gates.return_value = QualityReport(
            status="passed", results=[], summary_badge="Passed"
        )

        response = client.post(
            f"/api/content/drafts/{draft.id}/regenerate",
            json={"guidance": "Make it punchier"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["regeneration_count"] == 1

    def test_regenerate_at_limit_returns_409(self, client, db_session, sample_client):
        """POST /api/content/drafts/{id}/regenerate at limit returns 409."""
        draft = _make_draft(
            db_session, sample_client.id, regeneration_count=3
        )

        response = client.post(
            f"/api/content/drafts/{draft.id}/regenerate",
            json={"guidance": "More casual"},
        )

        assert response.status_code == 409


class TestRouterCalibrationEndpoints:
    """Tests for voice calibration API endpoints."""

    def test_start_calibration(self, client, db_session, sample_client):
        """POST /api/content/calibration/{id}/start creates session."""
        response = client.post(
            f"/api/content/calibration/{sample_client.id}/start",
            json={"total_rounds": 8},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["total_rounds"] == 8
        assert data["status"] == "in_progress"

    def test_generate_round(self, client, db_session, sample_client):
        """POST /api/content/calibration/{id}/round returns A/B options."""
        session = create_calibration_session(db_session, sample_client.id)
        db_session.flush()

        response = client.post(f"/api/content/calibration/{session.id}/round")

        assert response.status_code == 201
        data = response.json()
        assert "option_a" in data
        assert "option_b" in data

    def test_choose_round(self, client, db_session, sample_client):
        """POST .../round/{id}/choose records choice."""
        session = create_calibration_session(db_session, sample_client.id)
        cal_round = generate_calibration_round(db_session, session.id)

        response = client.post(
            f"/api/content/calibration/{session.id}/round/{cal_round.id}/choose",
            json={"selected": "a"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["selected"] == "a"
        assert data["voice_delta"] is not None


class TestRouterFormatEndpoints:
    """Tests for format adaptation API endpoints."""

    def test_get_format_weights(self, client, db_session, sample_client):
        """GET /api/content/formats/{id} returns weights."""
        response = client.get(
            f"/api/content/formats/{sample_client.id}?platform=instagram"
        )

        assert response.status_code == 200
        data = response.json()
        assert "weights" in data
        assert data["platform"] == "instagram"


class TestRouterEvergreenEndpoints:
    """Tests for evergreen bank API endpoints."""

    def test_list_evergreen(self, client, db_session, sample_client):
        """GET /api/content/evergreen/{id} returns unused entries."""
        draft = _make_draft(db_session, sample_client.id)
        _make_evergreen(db_session, sample_client.id, draft.id)

        response = client.get(f"/api/content/evergreen/{sample_client.id}")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1


class TestRouterAiLabelEndpoints:
    """Tests for AI label API endpoints."""

    def test_get_ai_label_rules(self, client):
        """GET /api/content/ai-labels/rules returns platform rules."""
        response = client.get("/api/content/ai-labels/rules")

        assert response.status_code == 200
        data = response.json()
        assert "facebook" in data
        assert "instagram" in data
