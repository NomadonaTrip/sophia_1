"""Tests for campaign auto-grouping, campaign metrics, and funnel tracking.

Tests auto_group_campaigns, compute_campaign_metrics, log_conversion_event,
compute_funnel_metrics, and compute_cac.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from sophia.analytics.campaigns import (
    auto_group_campaigns,
    compute_campaign_metrics,
    list_campaigns,
)
from sophia.analytics.funnel import (
    FUNNEL_STAGES,
    compute_cac,
    compute_funnel_metrics,
    log_conversion_event,
)
from sophia.analytics.models import (
    Campaign,
    CampaignMembership,
    ConversionEvent,
    EngagementMetric,
)
from sophia.content.models import ContentDraft


def _make_draft(db, client_id, pillar="Tips", status="published", published_at=None):
    """Helper to create a ContentDraft with required fields."""
    if published_at is None:
        published_at = datetime(2026, 2, 15, 10, 0, tzinfo=timezone.utc)
    draft = ContentDraft(
        client_id=client_id,
        platform="instagram",
        content_type="feed",
        copy="Test content for campaign",
        image_prompt="A campaign image",
        image_ratio="1:1",
        status=status,
        content_pillar=pillar,
        published_at=published_at,
    )
    db.add(draft)
    db.flush()
    return draft


def _make_metric(db, client_id, name, value, metric_date, draft_id=None):
    """Helper to create an EngagementMetric."""
    from sophia.analytics.models import ALGO_DEPENDENT

    m = EngagementMetric(
        client_id=client_id,
        content_draft_id=draft_id,
        platform="instagram",
        metric_name=name,
        metric_value=value,
        metric_date=metric_date,
        is_algorithm_dependent=name in ALGO_DEPENDENT,
        period="day",
    )
    db.add(m)
    db.flush()
    return m


class TestAutoGroupCampaigns:
    """Tests for auto_group_campaigns."""

    def test_groups_by_pillar_and_month(self, db_session, sample_client):
        """Drafts with same pillar in same month are grouped together."""
        cid = sample_client.id

        # Two drafts with same pillar in February
        _make_draft(
            db_session,
            cid,
            pillar="Tips",
            published_at=datetime(2026, 2, 10, 10, 0, tzinfo=timezone.utc),
        )
        _make_draft(
            db_session,
            cid,
            pillar="Tips",
            published_at=datetime(2026, 2, 20, 10, 0, tzinfo=timezone.utc),
        )
        # One draft with different pillar
        _make_draft(
            db_session,
            cid,
            pillar="Behind the Scenes",
            published_at=datetime(2026, 2, 15, 10, 0, tzinfo=timezone.utc),
        )

        campaigns = auto_group_campaigns(db_session, cid)

        assert len(campaigns) == 2
        names = {c.name for c in campaigns}
        assert "Tips - February 2026" in names
        assert "Behind the Scenes - February 2026" in names

        # Check memberships
        tips_campaign = next(c for c in campaigns if c.content_pillar == "Tips")
        memberships = (
            db_session.query(CampaignMembership)
            .filter_by(campaign_id=tips_campaign.id)
            .all()
        )
        assert len(memberships) == 2

    def test_does_not_regroup_already_grouped(self, db_session, sample_client):
        """Already-grouped drafts are skipped."""
        cid = sample_client.id

        d1 = _make_draft(db_session, cid, pillar="Tips")

        # First grouping
        campaigns_1 = auto_group_campaigns(db_session, cid)
        assert len(campaigns_1) == 1

        # Add another draft
        d2 = _make_draft(
            db_session,
            cid,
            pillar="Tips",
            published_at=datetime(2026, 2, 20, 10, 0, tzinfo=timezone.utc),
        )

        # Second grouping -- should only pick up d2
        campaigns_2 = auto_group_campaigns(db_session, cid)
        assert len(campaigns_2) == 1

        # d1's membership still exists, d2 was added to same campaign
        all_memberships = db_session.query(CampaignMembership).all()
        assert len(all_memberships) == 2

    def test_no_ungrouped_returns_empty(self, db_session, sample_client):
        """Returns empty list when no ungrouped drafts exist."""
        campaigns = auto_group_campaigns(db_session, sample_client.id)
        assert campaigns == []

    def test_different_months_create_separate_campaigns(
        self, db_session, sample_client
    ):
        """Same pillar in different months creates separate campaigns."""
        cid = sample_client.id

        _make_draft(
            db_session,
            cid,
            pillar="Tips",
            published_at=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
        )
        _make_draft(
            db_session,
            cid,
            pillar="Tips",
            published_at=datetime(2026, 2, 15, 10, 0, tzinfo=timezone.utc),
        )

        campaigns = auto_group_campaigns(db_session, cid)

        assert len(campaigns) == 2
        names = {c.name for c in campaigns}
        assert "Tips - January 2026" in names
        assert "Tips - February 2026" in names


class TestComputeCampaignMetrics:
    """Tests for compute_campaign_metrics."""

    def test_aggregates_correctly(self, db_session, sample_client):
        """Aggregate engagement metrics for campaign drafts."""
        cid = sample_client.id

        # Create drafts and group them
        d1 = _make_draft(db_session, cid, pillar="Tips")
        d2 = _make_draft(
            db_session,
            cid,
            pillar="Tips",
            published_at=datetime(2026, 2, 20, 10, 0, tzinfo=timezone.utc),
        )

        campaigns = auto_group_campaigns(db_session, cid)
        campaign = campaigns[0]

        # Add engagement metrics
        _make_metric(db_session, cid, "reach", 500, date(2026, 2, 15), d1.id)
        _make_metric(db_session, cid, "likes", 25, date(2026, 2, 15), d1.id)
        _make_metric(db_session, cid, "reach", 300, date(2026, 2, 20), d2.id)
        _make_metric(db_session, cid, "likes", 15, date(2026, 2, 20), d2.id)
        _make_metric(db_session, cid, "saved", 10, date(2026, 2, 20), d2.id)

        result = compute_campaign_metrics(db_session, campaign.id)

        assert result["total_reach"] == 800
        assert result["total_engagement"] == 50  # 25 + 15 + 10
        assert result["post_count"] == 2
        assert result["total_saves"] == 10
        # (50 / 800) * 100 = 6.25
        assert result["avg_engagement_rate"] == 6.25

    def test_empty_campaign_returns_zeros(self, db_session, sample_client):
        """Empty campaign returns zero metrics."""
        cid = sample_client.id

        campaign = Campaign(
            client_id=cid,
            name="Empty",
            slug="empty",
            start_date=date(2026, 2, 1),
            status="active",
        )
        db_session.add(campaign)
        db_session.flush()

        result = compute_campaign_metrics(db_session, campaign.id)

        assert result["total_reach"] == 0
        assert result["post_count"] == 0


class TestLogConversionEvent:
    """Tests for log_conversion_event."""

    def test_creates_record(self, db_session, sample_client):
        """Successfully creates and persists a conversion event."""
        event = log_conversion_event(
            db_session,
            sample_client.id,
            event_type="inquiry",
            source="operator_reported",
            details={"channel": "phone"},
        )

        assert event.id is not None
        assert event.event_type == "inquiry"
        assert event.source == "operator_reported"
        assert event.details == {"channel": "phone"}

        found = db_session.get(ConversionEvent, event.id)
        assert found is not None

    def test_invalid_event_type_raises(self, db_session, sample_client):
        """Invalid event type raises ValueError."""
        with pytest.raises(ValueError, match="Invalid event_type"):
            log_conversion_event(
                db_session,
                sample_client.id,
                event_type="invalid_stage",
                source="test",
            )


class TestComputeFunnelMetrics:
    """Tests for compute_funnel_metrics."""

    def test_computes_stage_counts_and_rates(self, db_session, sample_client):
        """Stage counts and conversion rates are computed correctly."""
        cid = sample_client.id

        # Create funnel events
        for _ in range(10):
            log_conversion_event(db_session, cid, "utm_click", "api")
        for _ in range(5):
            log_conversion_event(db_session, cid, "save", "api")
        for _ in range(2):
            log_conversion_event(db_session, cid, "inquiry", "api")
        log_conversion_event(db_session, cid, "conversion", "api")

        result = compute_funnel_metrics(
            db_session,
            cid,
            start_date=date.today() - timedelta(days=1),
            end_date=date.today() + timedelta(days=1),
        )

        assert result["stage_counts"]["utm_click"] == 10
        assert result["stage_counts"]["save"] == 5
        assert result["stage_counts"]["inquiry"] == 2
        assert result["stage_counts"]["conversion"] == 1
        assert result["total_events"] == 18

        # utm_click -> save: 5/10 = 50%
        assert result["conversion_rates"]["utm_click_to_save"] == 50.0


class TestComputeCAC:
    """Tests for compute_cac."""

    def test_returns_none_when_no_revenue(self, db_session, sample_client):
        """Returns None when no revenue data exists."""
        result = compute_cac(db_session, sample_client.id)
        assert result is None

    def test_computes_with_revenue_data(self, db_session, sample_client):
        """Computes CAC and CLV correctly with revenue data."""
        cid = sample_client.id

        # Create conversion events with revenue
        d1 = _make_draft(db_session, cid)
        d2 = _make_draft(
            db_session,
            cid,
            published_at=datetime(2026, 2, 20, 10, 0, tzinfo=timezone.utc),
        )

        log_conversion_event(
            db_session,
            cid,
            "conversion",
            "operator_reported",
            content_draft_id=d1.id,
            revenue_amount=500.0,
        )
        log_conversion_event(
            db_session,
            cid,
            "conversion",
            "operator_reported",
            content_draft_id=d2.id,
            revenue_amount=300.0,
        )

        result = compute_cac(db_session, cid)

        assert result is not None
        assert result["total_revenue"] == 800.0
        assert result["conversion_count"] == 2
        # CLV = 800 / 2 unique draft sources = 400
        assert result["clv"] == 400.0

    def test_returns_none_for_non_conversion_events(
        self, db_session, sample_client
    ):
        """Non-conversion events with revenue don't count."""
        cid = sample_client.id
        log_conversion_event(
            db_session, cid, "inquiry", "api", revenue_amount=100.0
        )

        result = compute_cac(db_session, cid)
        assert result is None
