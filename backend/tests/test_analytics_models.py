"""Tests for Phase 5 analytics ORM models.

Validates model creation, JSON column handling, algorithm classification
constants, and unique constraints.
"""

from datetime import date, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from sophia.analytics.models import (
    ALGO_DEPENDENT,
    ALGO_INDEPENDENT,
    Campaign,
    CampaignMembership,
    ConversionEvent,
    DecisionQualityScore,
    DecisionTrace,
    EngagementMetric,
    IndustryBenchmark,
    KPISnapshot,
)


class TestEngagementMetric:
    """EngagementMetric model tests."""

    def test_create_algo_dependent_metric(self, db_session, sample_client):
        """Algorithm-dependent metric (views) is created correctly."""
        metric = EngagementMetric(
            client_id=sample_client.id,
            platform="instagram",
            metric_name="views",
            metric_value=1500.0,
            metric_date=date(2026, 2, 28),
            is_algorithm_dependent=True,
            period="day",
            platform_post_id="ig_post_123",
        )
        db_session.add(metric)
        db_session.flush()

        assert metric.id is not None
        assert metric.is_algorithm_dependent is True
        assert metric.metric_value == 1500.0
        assert metric.platform == "instagram"

    def test_create_algo_independent_metric(self, db_session, sample_client):
        """Algorithm-independent metric (likes) is created correctly."""
        metric = EngagementMetric(
            client_id=sample_client.id,
            platform="facebook",
            metric_name="likes",
            metric_value=42.0,
            metric_date=date(2026, 2, 28),
            is_algorithm_dependent=False,
            period="day",
        )
        db_session.add(metric)
        db_session.flush()

        assert metric.id is not None
        assert metric.is_algorithm_dependent is False
        assert metric.content_draft_id is None

    def test_classification_constants(self):
        """ALGO_DEPENDENT and ALGO_INDEPENDENT sets are disjoint and comprehensive."""
        assert "views" in ALGO_DEPENDENT
        assert "reach" in ALGO_DEPENDENT
        assert "likes" in ALGO_INDEPENDENT
        assert "saved" in ALGO_INDEPENDENT
        assert "shares" in ALGO_INDEPENDENT
        # Sets should be disjoint
        assert ALGO_DEPENDENT & ALGO_INDEPENDENT == set()


class TestKPISnapshot:
    """KPISnapshot model tests."""

    def test_create_with_json_columns(self, db_session, sample_client):
        """KPISnapshot with JSON summary columns persists correctly."""
        snapshot = KPISnapshot(
            client_id=sample_client.id,
            week_start=date(2026, 2, 24),
            week_end=date(2026, 2, 28),
            engagement_rate=0.045,
            save_rate=0.012,
            approval_rate=0.85,
            algo_dependent_summary={"views": 5000, "reach": 3200},
            algo_independent_summary={"likes": 200, "shares": 15},
            custom_goals={"website_clicks": 50},
        )
        db_session.add(snapshot)
        db_session.flush()

        assert snapshot.id is not None
        assert snapshot.algo_dependent_summary["views"] == 5000
        assert snapshot.custom_goals["website_clicks"] == 50

    def test_nullable_fields(self, db_session, sample_client):
        """KPISnapshot with minimal fields (only required)."""
        snapshot = KPISnapshot(
            client_id=sample_client.id,
            week_start=date(2026, 2, 24),
            week_end=date(2026, 2, 28),
        )
        db_session.add(snapshot)
        db_session.flush()

        assert snapshot.id is not None
        assert snapshot.engagement_rate is None
        assert snapshot.algo_dependent_summary is None


class TestCampaign:
    """Campaign and CampaignMembership model tests."""

    def test_create_campaign(self, db_session, sample_client):
        """Campaign creation with all fields."""
        campaign = Campaign(
            client_id=sample_client.id,
            name="Spring Landscaping Tips",
            slug="spring-landscaping-tips",
            start_date=date(2026, 3, 1),
            content_pillar="education",
            topic="spring lawn care",
            status="active",
        )
        db_session.add(campaign)
        db_session.flush()

        assert campaign.id is not None
        assert campaign.status == "active"
        assert campaign.end_date is None

    def test_campaign_membership(self, db_session, sample_client):
        """CampaignMembership links campaign to draft."""
        campaign = Campaign(
            client_id=sample_client.id,
            name="Test Campaign",
            slug="test-campaign",
            start_date=date(2026, 3, 1),
        )
        db_session.add(campaign)
        db_session.flush()

        # Create a content draft to link
        from sophia.content.models import ContentDraft

        draft = ContentDraft(
            client_id=sample_client.id,
            platform="facebook",
            content_type="feed",
            copy="Test post copy",
            image_prompt="A beautiful garden scene",
            image_ratio="1:1",
            gate_status="passed",
            status="draft",
        )
        db_session.add(draft)
        db_session.flush()

        membership = CampaignMembership(
            campaign_id=campaign.id,
            content_draft_id=draft.id,
        )
        db_session.add(membership)
        db_session.flush()

        assert membership.id is not None
        assert membership.campaign_id == campaign.id
        assert membership.content_draft_id == draft.id


class TestConversionEvent:
    """ConversionEvent model tests."""

    def test_create_conversion_event(self, db_session, sample_client):
        """ConversionEvent with all fields including revenue."""
        event = ConversionEvent(
            client_id=sample_client.id,
            event_type="conversion",
            source="operator_reported",
            event_date=date(2026, 2, 28),
            details={"notes": "Client called after seeing post"},
            revenue_amount=500.0,
        )
        db_session.add(event)
        db_session.flush()

        assert event.id is not None
        assert event.revenue_amount == 500.0
        assert event.details["notes"] == "Client called after seeing post"

    def test_utm_click_event(self, db_session, sample_client):
        """UTM click event from platform API."""
        event = ConversionEvent(
            client_id=sample_client.id,
            event_type="utm_click",
            source="utm_tracking",
            event_date=date(2026, 2, 28),
            details={"utm_campaign": "spring-tips", "utm_content": "post_42"},
        )
        db_session.add(event)
        db_session.flush()

        assert event.id is not None
        assert event.content_draft_id is None


class TestDecisionTrace:
    """DecisionTrace model tests."""

    def test_create_with_json_payloads(self, db_session, sample_client):
        """DecisionTrace with full JSON evidence and predictions."""
        from sophia.content.models import ContentDraft

        draft = ContentDraft(
            client_id=sample_client.id,
            platform="instagram",
            content_type="feed",
            copy="Test post",
            image_prompt="Test image prompt",
            image_ratio="4:5",
            gate_status="passed",
            status="draft",
        )
        db_session.add(draft)
        db_session.flush()

        trace = DecisionTrace(
            content_draft_id=draft.id,
            client_id=sample_client.id,
            stage="angle",
            decision="Chose seasonal angle for spring",
            alternatives_considered=["product feature", "customer story"],
            rationale="Seasonal content performs 20% better historically",
            evidence={"historical_engagement_lift": 0.20},
            confidence=0.85,
            predicted_outcome={"engagement_rate": 0.05},
        )
        db_session.add(trace)
        db_session.flush()

        assert trace.id is not None
        assert trace.stage == "angle"
        assert trace.confidence == 0.85
        assert trace.actual_outcome is None  # filled post-performance


class TestDecisionQualityScore:
    """DecisionQualityScore model tests."""

    def test_create_quality_score(self, db_session, sample_client):
        """DecisionQualityScore creation with scores_detail."""
        score = DecisionQualityScore(
            client_id=sample_client.id,
            decision_type="topic_selection",
            period_start=date(2026, 2, 1),
            period_end=date(2026, 2, 28),
            sample_count=15,
            avg_quality_score=0.72,
            scores_detail={"relevance": 0.8, "timing": 0.65, "audience_fit": 0.71},
        )
        db_session.add(score)
        db_session.flush()

        assert score.id is not None
        assert score.avg_quality_score == 0.72
        assert score.scores_detail["relevance"] == 0.8


class TestIndustryBenchmark:
    """IndustryBenchmark model tests."""

    def test_create_benchmark(self, db_session):
        """IndustryBenchmark creation."""
        benchmark = IndustryBenchmark(
            vertical="landscaping",
            platform="instagram",
            metric_name="engagement_rate",
            benchmark_value=0.032,
            data_source="Sprout Social 2025 Report",
            data_date=date(2025, 6, 1),
        )
        db_session.add(benchmark)
        db_session.flush()

        assert benchmark.id is not None
        assert benchmark.benchmark_value == 0.032

    def test_unique_constraint(self, db_session):
        """Unique constraint on (vertical, platform, metric_name)."""
        b1 = IndustryBenchmark(
            vertical="restaurant",
            platform="facebook",
            metric_name="reach",
            benchmark_value=5000.0,
        )
        db_session.add(b1)
        db_session.flush()

        b2 = IndustryBenchmark(
            vertical="restaurant",
            platform="facebook",
            metric_name="reach",
            benchmark_value=6000.0,
        )
        db_session.add(b2)

        with pytest.raises(IntegrityError):
            db_session.flush()
