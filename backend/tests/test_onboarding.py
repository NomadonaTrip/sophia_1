"""Tests for onboarding state machine with multi-session resume and skip-and-flag.

All tests run against a SQLCipher-encrypted test database.
"""

from sophia.intelligence.onboarding import FIELD_GROUP_NAMES, OnboardingService
from sophia.intelligence.schemas import ClientCreate
from sophia.intelligence.service import ClientService


class TestOnboardingInitialization:
    """Tests for onboarding state initialization."""

    def test_initialize_onboarding(self, db_session, sample_client):
        """Verify onboarding state initialized with business_basics completed."""
        state = sample_client.onboarding_state
        assert state is not None
        assert "business_basics" in state["completed_fields"]
        assert "business_basics" not in state["pending_fields"]
        assert state["session_count"] == 1

        status = OnboardingService.get_onboarding_status(sample_client)
        # business_basics is 1 of 9 groups = ~11%
        assert status["percent_complete"] == 11


class TestOnboardingProgression:
    """Tests for onboarding field progression."""

    def test_onboarding_progression(self, db_session, sample_client):
        """Mark fields completed in sequence and verify state advances."""
        # Initial: business_basics done, geography is next
        status = OnboardingService.get_onboarding_status(sample_client)
        assert status["next_field_group"] == "geography"

        # Complete geography
        status = OnboardingService.mark_field_completed(
            db_session, sample_client, "geography"
        )
        assert "geography" in status["completed_fields"]
        assert status["next_field_group"] == "market_scope"

        # Complete market_scope
        status = OnboardingService.mark_field_completed(
            db_session, sample_client, "market_scope"
        )
        assert "market_scope" in status["completed_fields"]
        assert status["next_field_group"] == "content_strategy"

    def test_skip_and_flag(self, db_session, sample_client):
        """Skip a field and verify it moves to skipped_fields."""
        # Skip geography
        status = OnboardingService.skip_field(
            db_session, sample_client, "geography"
        )
        assert "geography" in status["skipped_fields"]
        assert "geography" not in status["pending_fields"]
        # Should advance past geography to market_scope
        assert status["next_field_group"] == "market_scope"

    def test_multi_session_resume(self, db_session, sample_client):
        """Verify state persists correctly for multi-session resume."""
        # Complete a few fields across "sessions"
        OnboardingService.mark_field_completed(
            db_session, sample_client, "geography"
        )
        OnboardingService.mark_field_completed(
            db_session, sample_client, "market_scope"
        )

        # Simulate session resume by re-querying
        db_session.refresh(sample_client)
        status = OnboardingService.get_onboarding_status(sample_client)

        assert "business_basics" in status["completed_fields"]
        assert "geography" in status["completed_fields"]
        assert "market_scope" in status["completed_fields"]
        assert status["next_field_group"] == "content_strategy"
        # 3 completed out of 9 = 33%
        assert status["percent_complete"] == 33

    def test_get_next_question_context(self, db_session, sample_client):
        """Verify correct next field group returned with coaching context."""
        context = OnboardingService.get_next_question_context(sample_client)

        assert context["field_group"] == "geography"
        assert context["label"] == "Geography"
        assert "location" in context["why"].lower() or "local" in context["why"].lower()
        assert len(context["fields"]) > 0
        assert context["suggestions_placeholder"] is not None

    def test_interleaved_onboarding(self, db_session, sample_client, sample_client_2):
        """Two clients at different onboarding stages maintain independent state."""
        # Advance client 1 through geography + market_scope
        OnboardingService.mark_field_completed(
            db_session, sample_client, "geography"
        )
        OnboardingService.mark_field_completed(
            db_session, sample_client, "market_scope"
        )

        # Advance client 2 through geography only
        OnboardingService.mark_field_completed(
            db_session, sample_client_2, "geography"
        )

        # Verify independent states
        status_1 = OnboardingService.get_onboarding_status(sample_client)
        status_2 = OnboardingService.get_onboarding_status(sample_client_2)

        assert len(status_1["completed_fields"]) == 3  # basics + geo + market
        assert len(status_2["completed_fields"]) == 2  # basics + geo

        assert status_1["next_field_group"] == "content_strategy"
        assert status_2["next_field_group"] == "market_scope"

    def test_complete_all_fields(self, db_session, sample_client):
        """Completing all field groups sets phase to 'complete'."""
        # Complete all remaining groups
        for group in FIELD_GROUP_NAMES:
            if group != "business_basics":  # Already completed
                OnboardingService.mark_field_completed(
                    db_session, sample_client, group
                )

        status = OnboardingService.get_onboarding_status(sample_client)
        assert status["percent_complete"] == 100
        assert status["next_field_group"] is None
        assert len(status["pending_fields"]) == 0
