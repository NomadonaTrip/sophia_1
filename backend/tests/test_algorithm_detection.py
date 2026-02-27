"""Tests for cross-portfolio algorithm detection and platform playbook.

Tests algorithm shift detection using MAD-based z-scores, industry news
cross-referencing, gradual adaptation proposals, full decision trail
logging, and living platform playbook management.
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from sophia.intelligence.models import Client
from sophia.intelligence.schemas import ClientCreate
from sophia.intelligence.service import ClientService
from sophia.research.algorithm import (
    analyze_shift_nature,
    detect_algorithm_shift,
    log_algorithm_event,
    propose_adaptation,
)
from sophia.research.models import (
    FindingType,
    PlatformIntelligence,
    ResearchFinding,
)
from sophia.research.playbook import (
    categorize_insight,
    get_platform_playbook,
    merge_algorithm_shift_into_playbook,
    update_playbook,
)


class TestDetectAlgorithmShift:
    """Tests for detect_algorithm_shift using MAD-based z-scores."""

    def test_uniform_decline_across_5_clients_detected(self):
        """Uniform decline across 5 clients triggers algorithm shift detection."""
        # All clients see ~25% decline (with minor variance)
        deltas = {
            1: -0.24,
            2: -0.26,
            3: -0.23,
            4: -0.27,
            5: -0.25,
        }

        result = detect_algorithm_shift(deltas)

        assert result is not None
        assert result["detected"] is True
        assert result["direction"] == "decline"
        assert result["magnitude_pct"] < 0
        assert result["affected_client_count"] >= 4
        assert result["total_clients"] == 5
        assert result["confidence"] in ("high", "medium")

    def test_one_outlier_among_5_detected_outlier_excluded(self):
        """One outlier client doesn't prevent detection of uniform shift."""
        # 4 clients decline similarly, 1 outlier has a big spike
        deltas = {
            1: -0.25,
            2: -0.23,
            3: -0.27,
            4: -0.24,
            5: 0.50,  # Outlier
        }

        result = detect_algorithm_shift(deltas)

        assert result is not None
        assert result["detected"] is True
        assert result["direction"] == "decline"
        # The outlier should have a high z-score, but the 4 uniform clients
        # should still be detected
        assert result["affected_client_count"] >= 3

    def test_fewer_than_3_clients_returns_none(self):
        """Fewer than 3 clients returns None (minimum threshold)."""
        deltas = {1: -0.25, 2: -0.27}

        result = detect_algorithm_shift(deltas)

        assert result is None

    def test_mixed_signals_no_uniform_pattern_returns_none(self):
        """Mixed signals with no uniform pattern returns None."""
        # Clients going in different directions with no clear pattern
        deltas = {
            1: 0.30,
            2: -0.25,
            3: 0.10,
            4: -0.40,
            5: 0.05,
        }

        result = detect_algorithm_shift(deltas)

        # Mixed signals: median is close to 0, so abs(median) <= 0.1
        # This should return None
        assert result is None

    def test_all_identical_values_mad_zero_returns_none(self):
        """All identical values (MAD=0) returns None."""
        deltas = {
            1: -0.20,
            2: -0.20,
            3: -0.20,
            4: -0.20,
            5: -0.20,
        }

        result = detect_algorithm_shift(deltas)

        # MAD is 0 when all values are identical
        assert result is None

    def test_uniform_increase_detected(self):
        """Uniform engagement increase also detected as algorithm shift."""
        deltas = {
            1: 0.30,
            2: 0.28,
            3: 0.32,
            4: 0.29,
            5: 0.31,
        }

        result = detect_algorithm_shift(deltas)

        assert result is not None
        assert result["detected"] is True
        assert result["direction"] == "increase"
        assert result["magnitude_pct"] > 0

    def test_small_magnitude_returns_none(self):
        """Very small uniform change (<=0.1) is ignored as noise."""
        deltas = {
            1: 0.05,
            2: 0.04,
            3: 0.06,
            4: 0.05,
            5: 0.04,
        }

        result = detect_algorithm_shift(deltas)

        assert result is None


class TestAnalyzeShiftNature:
    """Tests for analyze_shift_nature cross-referencing industry news."""

    def test_cross_references_with_industry_news(self, db_session, sample_client):
        """analyze_shift_nature finds corroborating industry news."""
        # Create industry finding about algorithm change
        finding = ResearchFinding(
            client_id=sample_client.id,
            finding_type=FindingType.INDUSTRY,
            topic="Instagram algorithm update February 2026",
            summary="Instagram rolls out new algorithm change affecting engagement and reach distribution for business accounts",
            source_name="Social Media Today",
            confidence=0.9,
        )
        db_session.add(finding)
        db_session.commit()

        shift_data = {
            "detected": True,
            "direction": "decline",
            "magnitude_pct": -0.25,
            "affected_client_count": 4,
            "total_clients": 5,
            "confidence": "high",
        }

        result = analyze_shift_nature(db_session, "instagram", shift_data)

        assert result["platform"] == "instagram"
        assert result["industry_corroboration"] is True
        assert "Social Media Today" in result["corroborating_sources"]
        assert result["shift_type"] in ("reach", "engagement", "both")
        assert result["confidence"] in ("high", "medium", "low")

    def test_no_corroboration_returns_low_confidence(self, db_session, sample_client):
        """No industry corroboration results in lower confidence."""
        shift_data = {
            "detected": True,
            "direction": "decline",
            "magnitude_pct": -0.15,
            "affected_client_count": 3,
            "total_clients": 5,
            "confidence": "medium",
        }

        result = analyze_shift_nature(db_session, "facebook", shift_data)

        assert result["industry_corroboration"] is False
        assert result["corroborating_sources"] == []
        assert result["confidence"] == "low"

    def test_classifies_reach_vs_engagement(self, db_session, sample_client):
        """Correctly classifies shift as reach-related based on news content."""
        finding = ResearchFinding(
            client_id=sample_client.id,
            finding_type=FindingType.INDUSTRY,
            topic="Facebook reach algorithm update",
            summary="Facebook algorithm change reduces organic reach and impression distribution for pages",
            source_name="TechCrunch",
            confidence=0.85,
        )
        db_session.add(finding)
        db_session.commit()

        shift_data = {
            "detected": True,
            "direction": "decline",
            "magnitude_pct": -0.20,
            "confidence": "high",
        }

        result = analyze_shift_nature(db_session, "facebook", shift_data)

        assert result["shift_type"] == "reach"


class TestProposeAdaptation:
    """Tests for propose_adaptation generating gradual content shift proposals."""

    def test_generates_gradual_shift_proposal(self, db_session):
        """Proposal includes 20-30% shift with all required fields."""
        shift_data = {
            "direction": "decline",
            "magnitude_pct": -0.25,
            "affected_client_count": 4,
            "total_clients": 5,
        }
        shift_nature = {
            "platform": "instagram",
            "shift_type": "engagement",
        }

        result = propose_adaptation(
            db_session, "instagram", shift_data, shift_nature
        )

        assert result["platform"] == "instagram"
        assert result["hypothesis"]
        assert 20 <= result["shift_percentage"] <= 30
        assert result["duration_days"] in (7, 14)
        assert result["success_metric"]
        assert result["rollback_plan"]
        assert result["requires_operator_approval"] is True
        assert len(result["increase_content_types"]) > 0
        assert len(result["decrease_content_types"]) > 0

    def test_higher_magnitude_yields_larger_shift(self, db_session):
        """Higher magnitude shifts recommend larger content changes."""
        # Small magnitude
        small_shift = propose_adaptation(
            db_session,
            "instagram",
            {"direction": "decline", "magnitude_pct": -0.15},
            {"shift_type": "engagement"},
        )

        # Large magnitude
        large_shift = propose_adaptation(
            db_session,
            "instagram",
            {"direction": "decline", "magnitude_pct": -0.35},
            {"shift_type": "engagement"},
        )

        assert large_shift["shift_percentage"] >= small_shift["shift_percentage"]

    def test_reach_vs_engagement_different_recommendations(self, db_session):
        """Reach shifts recommend different content types than engagement shifts."""
        shift_data = {"direction": "decline", "magnitude_pct": -0.25}

        reach_result = propose_adaptation(
            db_session, "instagram", shift_data, {"shift_type": "reach"}
        )
        engagement_result = propose_adaptation(
            db_session, "instagram", shift_data, {"shift_type": "engagement"}
        )

        # Different content type recommendations
        assert reach_result["increase_content_types"] != engagement_result["increase_content_types"]


class TestLogAlgorithmEvent:
    """Tests for log_algorithm_event creating PlatformIntelligence records."""

    def test_creates_platform_intelligence_record(self, db_session, sample_client):
        """log_algorithm_event creates a PlatformIntelligence record with full trail."""
        shift_data = {
            "detected": True,
            "direction": "decline",
            "magnitude_pct": -0.25,
            "affected_client_count": 4,
            "total_clients": 5,
            "confidence": "high",
        }
        shift_nature = {
            "platform": "instagram",
            "shift_type": "engagement",
            "industry_corroboration": True,
            "corroborating_sources": ["Social Media Today"],
            "confidence": "high",
        }
        adaptation = {
            "platform": "instagram",
            "hypothesis": "Test hypothesis",
            "shift_percentage": 25,
        }

        with patch("sophia.semantic.sync.sync_to_lance"):
            records = log_algorithm_event(
                db_session,
                "instagram",
                shift_data,
                shift_nature,
                adaptation,
                client_ids=[sample_client.id],
            )

        # Verify records were created
        assert len(records) >= 1
        record = records[0]
        assert record.category == "required_to_play"
        assert "Algorithm shift detected" in record.insight
        assert "decline" in record.insight
        assert record.evidence is not None
        assert "shift_data" in record.evidence
        assert "shift_nature" in record.evidence
        assert "adaptation_proposed" in record.evidence
        assert record.client_id == sample_client.id


class TestLogAlgorithmEventPlaybookWiring:
    """Tests for log_algorithm_event calling merge_algorithm_shift_into_playbook."""

    def test_calls_merge_algorithm_shift_into_playbook(self, db_session, sample_client):
        """log_algorithm_event calls merge_algorithm_shift_into_playbook after logging."""
        shift_data = {
            "detected": True,
            "direction": "decline",
            "magnitude_pct": -0.25,
            "affected_client_count": 4,
            "total_clients": 5,
            "confidence": "high",
        }
        shift_nature = {
            "platform": "instagram",
            "shift_type": "engagement",
            "industry_corroboration": True,
            "corroborating_sources": ["Social Media Today"],
            "confidence": "high",
        }
        adaptation = {
            "platform": "instagram",
            "hypothesis": "Test hypothesis",
            "shift_percentage": 25,
        }

        with (
            patch("sophia.semantic.sync.sync_to_lance"),
            patch(
                "sophia.research.playbook.merge_algorithm_shift_into_playbook",
                return_value=[],
            ) as mock_merge,
        ):
            records = log_algorithm_event(
                db_session,
                "instagram",
                shift_data,
                shift_nature,
                adaptation,
                client_ids=[sample_client.id],
            )

        assert len(records) >= 1
        mock_merge.assert_called_once_with(
            db_session, "instagram", shift_data, adaptation
        )

    def test_playbook_failure_does_not_prevent_logging(self, db_session, sample_client):
        """If merge_algorithm_shift_into_playbook raises, records are still returned."""
        shift_data = {
            "detected": True,
            "direction": "decline",
            "magnitude_pct": -0.25,
            "affected_client_count": 4,
            "total_clients": 5,
            "confidence": "high",
        }
        shift_nature = {
            "platform": "instagram",
            "shift_type": "engagement",
            "industry_corroboration": False,
            "corroborating_sources": [],
            "confidence": "medium",
        }
        adaptation = {
            "platform": "instagram",
            "hypothesis": "Test hypothesis",
            "shift_percentage": 20,
        }

        with (
            patch("sophia.semantic.sync.sync_to_lance"),
            patch(
                "sophia.research.playbook.merge_algorithm_shift_into_playbook",
                side_effect=RuntimeError("Playbook merge failed"),
            ),
        ):
            records = log_algorithm_event(
                db_session,
                "instagram",
                shift_data,
                shift_nature,
                adaptation,
                client_ids=[sample_client.id],
            )

        # Records should still be returned despite playbook failure
        assert len(records) >= 1
        assert records[0].category == "required_to_play"


class TestUpdatePlaybook:
    """Tests for update_playbook creating and deactivating insights."""

    def test_creates_new_insight(self, db_session, sample_client):
        """update_playbook creates a new PlatformIntelligence record."""
        with patch("sophia.semantic.sync.sync_to_lance"):
            record = update_playbook(
                db_session,
                client_id=sample_client.id,
                platform="instagram",
                insight="Use Reels for maximum reach",
                evidence={"engagement_lift": 0.35},
                category="required_to_play",
            )

        assert record.id is not None
        assert record.client_id == sample_client.id
        assert record.platform == "instagram"
        assert record.insight == "Use Reels for maximum reach"
        assert record.category == "required_to_play"
        assert record.is_active == 1

    def test_deactivates_conflicting_insights(self, db_session, sample_client):
        """update_playbook deactivates old insights when new one conflicts."""
        with patch("sophia.semantic.sync.sync_to_lance"):
            # Create initial insight
            old_record = update_playbook(
                db_session,
                client_id=sample_client.id,
                platform="instagram",
                insight="Use Reels for maximum reach on Instagram",
                evidence={"engagement_lift": 0.35},
                category="required_to_play",
            )
            old_id = old_record.id

            # Create conflicting insight (overlapping keywords)
            new_record = update_playbook(
                db_session,
                client_id=sample_client.id,
                platform="instagram",
                insight="Use Reels and Stories for maximum reach on Instagram",
                evidence={"engagement_lift": 0.45},
                category="required_to_play",
            )

        # Old record should be deactivated
        db_session.refresh(old_record)
        assert old_record.is_active == 0
        assert new_record.is_active == 1


class TestGetPlatformPlaybook:
    """Tests for get_platform_playbook returning organized insights."""

    def test_returns_organized_by_category(self, db_session, sample_client):
        """Playbook returns insights organized by required_to_play and sufficient_to_win."""
        with patch("sophia.semantic.sync.sync_to_lance"):
            update_playbook(
                db_session,
                client_id=sample_client.id,
                platform="facebook",
                insight="Post at least 3 times per week",
                evidence={"min_frequency": 3},
                category="required_to_play",
            )
            update_playbook(
                db_session,
                client_id=sample_client.id,
                platform="facebook",
                insight="Best posting time is 2-4pm for maximum engagement",
                evidence={"best_hour": 14, "engagement_lift": 0.20},
                category="sufficient_to_win",
            )

        playbook = get_platform_playbook(
            db_session, sample_client.id, "facebook"
        )

        assert "required_to_play" in playbook
        assert "sufficient_to_win" in playbook
        assert len(playbook["required_to_play"]) == 1
        assert len(playbook["sufficient_to_win"]) == 1
        assert playbook["required_to_play"][0]["insight"] == "Post at least 3 times per week"
        assert "Best posting time" in playbook["sufficient_to_win"][0]["insight"]

    def test_excludes_inactive_insights(self, db_session, sample_client):
        """Playbook only returns active insights."""
        # Create and deactivate an insight
        record = PlatformIntelligence(
            client_id=sample_client.id,
            platform="instagram",
            category="required_to_play",
            insight="Old deactivated insight",
            evidence={},
            is_active=0,
        )
        db_session.add(record)
        db_session.commit()

        playbook = get_platform_playbook(
            db_session, sample_client.id, "instagram"
        )

        all_insights = playbook["required_to_play"] + playbook["sufficient_to_win"]
        assert len(all_insights) == 0


class TestCategorizeInsight:
    """Tests for categorize_insight classification."""

    def test_classifies_required_to_play(self):
        """Insights about requirements are classified as required_to_play."""
        insight = "Must include alt text on all images for accessibility compliance"
        evidence = {"compliance": True}

        result = categorize_insight(insight, evidence)

        assert result == "required_to_play"

    def test_classifies_sufficient_to_win(self):
        """Insights about competitive advantage are classified as sufficient_to_win."""
        insight = "Posting at optimal time of 2pm yields highest engagement and growth"
        evidence = {"engagement_lift": 0.35}

        result = categorize_insight(insight, evidence)

        assert result == "sufficient_to_win"

    def test_evidence_influences_categorization(self):
        """Evidence data can influence categorization decision."""
        insight = "Include hashtags in posts"
        evidence_required = {"penalty": "posts without hashtags get 50% less reach"}
        evidence_win = {"improvement": "hashtags boost engagement by 15%"}

        result_required = categorize_insight(insight, evidence_required)
        result_win = categorize_insight(insight, evidence_win)

        assert result_required == "required_to_play"
        assert result_win == "sufficient_to_win"


class TestMergeAlgorithmShiftIntoPlaybook:
    """Tests for merge_algorithm_shift_into_playbook updating all clients."""

    def test_creates_entries_for_all_clients(self, db_session):
        """Merging creates required_to_play entries for all active clients."""
        # Create multiple clients
        c1 = ClientService.create_client(
            db_session, ClientCreate(name="Client Alpha", industry="Retail")
        )
        c2 = ClientService.create_client(
            db_session, ClientCreate(name="Client Beta", industry="Food")
        )
        c3 = ClientService.create_client(
            db_session, ClientCreate(name="Client Gamma", industry="Tech")
        )

        shift_data = {
            "direction": "decline",
            "magnitude_pct": -0.25,
            "affected_client_count": 3,
            "total_clients": 3,
        }
        adaptation = {
            "shift_percentage": 25,
            "increase_content_types": ["video/reels", "stories"],
            "decrease_content_types": ["static posts"],
        }

        records = merge_algorithm_shift_into_playbook(
            db_session, "instagram", shift_data, adaptation
        )

        assert len(records) >= 3
        for record in records:
            assert record.category == "required_to_play"
            assert record.platform == "instagram"
            assert "Algorithm shift" in record.insight
            assert record.is_active == 1
