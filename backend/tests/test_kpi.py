"""Tests for KPI computation service.

Tests weekly KPI computation, trends, benchmark comparison,
and posting time performance analysis.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from sophia.analytics.kpi import (
    compare_to_benchmark,
    compute_kpi_trends,
    compute_posting_time_performance,
    compute_weekly_kpis,
)
from sophia.analytics.models import (
    EngagementMetric,
    IndustryBenchmark,
    KPISnapshot,
)
from sophia.approval.models import ApprovalEvent
from sophia.content.models import ContentDraft


def _make_metric(
    db, client_id, name, value, metric_date, draft_id=None, platform="instagram"
):
    """Helper to create an EngagementMetric."""
    from sophia.analytics.models import ALGO_DEPENDENT

    m = EngagementMetric(
        client_id=client_id,
        content_draft_id=draft_id,
        platform=platform,
        metric_name=name,
        metric_value=value,
        metric_date=metric_date,
        is_algorithm_dependent=name in ALGO_DEPENDENT,
        period="day",
    )
    db.add(m)
    db.flush()
    return m


def _make_draft(db, client_id, status="published", published_at=None, **kwargs):
    """Helper to create a ContentDraft."""
    draft = ContentDraft(
        client_id=client_id,
        platform="instagram",
        content_type="feed",
        copy="Test post content",
        image_prompt="A test image",
        image_ratio="1:1",
        status=status,
        published_at=published_at,
        **kwargs,
    )
    db.add(draft)
    db.flush()
    return draft


class TestComputeWeeklyKPIs:
    """Tests for compute_weekly_kpis."""

    def test_computes_engagement_rate(self, db_session, sample_client):
        """Standard engagement KPIs computed from metric data."""
        week_end = date(2026, 2, 28)
        cid = sample_client.id

        # Create reach + engagement metrics within the week
        _make_metric(db_session, cid, "reach", 1000, date(2026, 2, 25))
        _make_metric(db_session, cid, "likes", 50, date(2026, 2, 25))
        _make_metric(db_session, cid, "comments", 10, date(2026, 2, 25))
        _make_metric(db_session, cid, "shares", 5, date(2026, 2, 25))
        _make_metric(db_session, cid, "saved", 15, date(2026, 2, 25))

        snapshot = compute_weekly_kpis(db_session, cid, week_end)

        assert snapshot.client_id == cid
        assert snapshot.week_start == date(2026, 2, 22)
        assert snapshot.week_end == week_end
        # (50 + 10 + 5 + 15) / 1000 * 100 = 8.0
        assert snapshot.engagement_rate == 8.0
        assert snapshot.save_rate == 1.5  # 15/1000 * 100
        assert snapshot.share_rate == 0.5  # 5/1000 * 100

    def test_computes_approval_rate_from_events(self, db_session, sample_client):
        """Internal quality KPIs from ApprovalEvent data."""
        week_end = date(2026, 2, 28)
        cid = sample_client.id

        # Create a draft and approval events
        draft = _make_draft(db_session, cid, status="approved")

        for action in ["approved", "approved", "rejected"]:
            event = ApprovalEvent(
                content_draft_id=draft.id,
                client_id=cid,
                action=action,
                actor="tayo",
                old_status="in_review",
                new_status=action,
            )
            db_session.add(event)
        db_session.flush()

        snapshot = compute_weekly_kpis(db_session, cid, week_end)

        # 2 approved / 3 total = 66.67%
        assert snapshot.approval_rate == pytest.approx(66.67, abs=0.01)
        # 1 rejected / 3 total = 33.33%
        assert snapshot.rejection_rate == pytest.approx(33.33, abs=0.01)

    def test_no_data_returns_null_values(self, db_session, sample_client):
        """Graceful degradation with no metric data."""
        week_end = date(2026, 2, 28)
        snapshot = compute_weekly_kpis(
            db_session, sample_client.id, week_end
        )

        assert snapshot.engagement_rate is None
        assert snapshot.save_rate is None
        assert snapshot.share_rate is None
        assert snapshot.reach_growth_pct is None
        assert snapshot.follower_growth_pct is None
        assert snapshot.approval_rate is None
        assert snapshot.rejection_rate is None

    def test_persists_snapshot_to_db(self, db_session, sample_client):
        """Snapshot is persisted and queryable."""
        week_end = date(2026, 2, 28)
        cid = sample_client.id

        _make_metric(db_session, cid, "reach", 500, date(2026, 2, 25))

        snapshot = compute_weekly_kpis(db_session, cid, week_end)

        found = (
            db_session.query(KPISnapshot)
            .filter_by(client_id=cid, week_end=week_end)
            .first()
        )
        assert found is not None
        assert found.id == snapshot.id

    def test_algo_summaries_populated(self, db_session, sample_client):
        """Algorithm-dependent and independent summaries are computed."""
        week_end = date(2026, 2, 28)
        cid = sample_client.id

        _make_metric(db_session, cid, "reach", 1000, date(2026, 2, 25))
        _make_metric(db_session, cid, "likes", 50, date(2026, 2, 25))

        snapshot = compute_weekly_kpis(db_session, cid, week_end)

        assert snapshot.algo_dependent_summary is not None
        assert "reach" in snapshot.algo_dependent_summary
        assert snapshot.algo_independent_summary is not None
        assert "likes" in snapshot.algo_independent_summary


class TestComputeKPITrends:
    """Tests for compute_kpi_trends."""

    def test_returns_multiple_weeks_ordered(self, db_session, sample_client):
        """Returns KPI snapshots ordered chronologically."""
        cid = sample_client.id

        # Create 3 snapshots in different weeks
        for i in range(3):
            we = date(2026, 2, 14 + i * 7)
            ws = we - timedelta(days=6)
            snap = KPISnapshot(
                client_id=cid,
                week_start=ws,
                week_end=we,
                engagement_rate=float(i + 1),
            )
            db_session.add(snap)
        db_session.flush()

        trends = compute_kpi_trends(db_session, cid, weeks=4)

        assert len(trends) == 3
        # Ordered by week_end ascending
        assert trends[0].week_end < trends[1].week_end < trends[2].week_end

    def test_limits_to_requested_weeks(self, db_session, sample_client):
        """Returns at most N weeks."""
        cid = sample_client.id

        base = date(2026, 1, 7)
        for i in range(5):
            we = base + timedelta(weeks=i)
            ws = we - timedelta(days=6)
            db_session.add(
                KPISnapshot(
                    client_id=cid, week_start=ws, week_end=we
                )
            )
        db_session.flush()

        trends = compute_kpi_trends(db_session, cid, weeks=3)
        assert len(trends) == 3


class TestCompareToBenchmark:
    """Tests for compare_to_benchmark."""

    def test_matching_vertical_returns_comparison(self, db_session, sample_client):
        """Returns comparison when benchmark exists for client vertical."""
        cid = sample_client.id

        # Set client vertical
        sample_client.industry_vertical = "restaurants"
        db_session.flush()

        # Create benchmark
        bm = IndustryBenchmark(
            vertical="restaurants",
            platform="instagram",
            metric_name="engagement_rate",
            benchmark_value=3.5,
        )
        db_session.add(bm)
        db_session.flush()

        # Create KPI snapshot
        kpi = KPISnapshot(
            client_id=cid,
            week_start=date(2026, 2, 22),
            week_end=date(2026, 2, 28),
            engagement_rate=5.0,
        )
        db_session.add(kpi)
        db_session.flush()

        result = compare_to_benchmark(db_session, cid, kpi)

        assert "engagement_rate" in result
        assert result["engagement_rate"]["client_value"] == 5.0
        assert result["engagement_rate"]["benchmark_value"] == 3.5
        assert result["engagement_rate"]["is_above"] is True
        # (5.0 - 3.5) / 3.5 * 100 = 42.86%
        assert result["engagement_rate"]["delta_pct"] == pytest.approx(
            42.86, abs=0.01
        )

    def test_no_benchmark_returns_empty(self, db_session, sample_client):
        """Returns empty dict when no benchmark exists."""
        cid = sample_client.id
        sample_client.industry_vertical = "nonexistent_vertical"
        db_session.flush()

        kpi = KPISnapshot(
            client_id=cid,
            week_start=date(2026, 2, 22),
            week_end=date(2026, 2, 28),
            engagement_rate=5.0,
        )
        db_session.add(kpi)
        db_session.flush()

        result = compare_to_benchmark(db_session, cid, kpi)
        assert result == {}

    def test_no_vertical_returns_empty(self, db_session, sample_client):
        """Returns empty dict when client has no industry_vertical."""
        cid = sample_client.id

        kpi = KPISnapshot(
            client_id=cid,
            week_start=date(2026, 2, 22),
            week_end=date(2026, 2, 28),
        )
        db_session.add(kpi)
        db_session.flush()

        result = compare_to_benchmark(db_session, cid, kpi)
        assert result == {}


class TestPostingTimePerformance:
    """Tests for compute_posting_time_performance."""

    def test_groups_by_hour(self, db_session, sample_client):
        """Groups engagement rates by posting hour."""
        cid = sample_client.id

        # Create 2 drafts at different hours
        d1 = _make_draft(
            db_session,
            cid,
            published_at=datetime(2026, 2, 25, 9, 0, tzinfo=timezone.utc),
        )
        d2 = _make_draft(
            db_session,
            cid,
            published_at=datetime(2026, 2, 26, 14, 0, tzinfo=timezone.utc),
        )

        # Add metrics for each draft
        _make_metric(
            db_session, cid, "likes", 20, date(2026, 2, 25), draft_id=d1.id
        )
        _make_metric(
            db_session, cid, "reach", 200, date(2026, 2, 25), draft_id=d1.id
        )
        _make_metric(
            db_session, cid, "likes", 40, date(2026, 2, 26), draft_id=d2.id
        )
        _make_metric(
            db_session, cid, "reach", 400, date(2026, 2, 26), draft_id=d2.id
        )

        result = compute_posting_time_performance(
            db_session, cid, "instagram"
        )

        assert 9 in result
        assert 14 in result
        # Hour 9: 20/200 * 100 = 10.0
        assert result[9] == 10.0
        # Hour 14: 40/400 * 100 = 10.0
        assert result[14] == 10.0

    def test_no_published_drafts_returns_empty(self, db_session, sample_client):
        """Returns empty dict when no published drafts exist."""
        result = compute_posting_time_performance(
            db_session, sample_client.id, "instagram"
        )
        assert result == {}
