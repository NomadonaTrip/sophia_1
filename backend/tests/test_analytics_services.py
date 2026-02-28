"""Tests for analytics service modules: sentiment, anomaly, ICP, SOV, briefing.

Tests VADER sentiment analysis, MAD-based anomaly detection, ICP comparison,
share of voice computation, and briefing content generation.
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from sophia.analytics.anomaly import (
    detect_client_anomalies,
    detect_metric_anomaly,
)
from sophia.analytics.briefing import (
    generate_morning_brief,
    generate_telegram_digest,
)
from sophia.analytics.icp import compare_audience_to_icp
from sophia.analytics.models import EngagementMetric, KPISnapshot
from sophia.analytics.sentiment import analyze_comment_sentiment
from sophia.analytics.sov import compute_share_of_voice
from sophia.content.models import ContentDraft
from sophia.research.models import Competitor, CompetitorSnapshot


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


def _make_draft(db, client_id, pillar="Tips", status="published", published_at=None):
    """Helper to create a ContentDraft."""
    if published_at is None:
        published_at = datetime(2026, 2, 15, 10, 0, tzinfo=timezone.utc)
    draft = ContentDraft(
        client_id=client_id,
        platform="instagram",
        content_type="feed",
        copy="Test content",
        image_prompt="Test image",
        image_ratio="1:1",
        status=status,
        content_pillar=pillar,
        published_at=published_at,
    )
    db.add(draft)
    db.flush()
    return draft


# -- Sentiment tests -----------------------------------------------------------


class TestAnalyzeCommentSentiment:
    """Tests for analyze_comment_sentiment."""

    def test_mixed_positive_negative(self):
        """Correctly classifies mixed positive and negative comments."""
        comments = [
            "This is amazing! Love it!",
            "Great content, very helpful",
            "Terrible, worst post ever",
            "Not bad, could be better",
            "Absolutely wonderful experience",
        ]

        result = analyze_comment_sentiment(comments)

        assert result["total_comments"] == 5
        assert result["positive_pct"] > 0
        assert result["negative_pct"] > 0
        # Majority are positive, so avg_compound should be positive
        assert result["avg_compound"] > 0
        # All percentages should sum to 100
        total_pct = (
            result["positive_pct"]
            + result["negative_pct"]
            + result["neutral_pct"]
        )
        assert total_pct == pytest.approx(100.0, abs=0.2)

    def test_empty_list_returns_zeros(self):
        """Empty comment list returns zero values."""
        result = analyze_comment_sentiment([])

        assert result["total_comments"] == 0
        assert result["positive_pct"] == 0.0
        assert result["negative_pct"] == 0.0
        assert result["neutral_pct"] == 0.0
        assert result["avg_compound"] == 0.0

    def test_all_positive(self):
        """All positive comments return 100% positive."""
        comments = [
            "Absolutely amazing!",
            "Love this so much!",
            "Best thing I've seen today!",
        ]

        result = analyze_comment_sentiment(comments)

        assert result["positive_pct"] == 100.0
        assert result["negative_pct"] == 0.0
        assert result["avg_compound"] > 0.05


# -- Anomaly detection tests --------------------------------------------------


class TestDetectMetricAnomaly:
    """Tests for detect_metric_anomaly."""

    def test_spike_detected(self):
        """Detects spike when value is significantly above median."""
        # Normal values around 100, then a spike
        values = [100, 102, 98, 101, 99, 103, 97]
        current = 200  # Massive spike

        result = detect_metric_anomaly(values, current)

        assert result is not None
        assert result["anomaly"] is True
        assert result["direction"] == "spike"
        assert result["z_score"] > 2.5

    def test_drop_detected(self):
        """Detects drop when value is significantly below median."""
        values = [100, 102, 98, 101, 99, 103, 97]
        current = 10  # Massive drop

        result = detect_metric_anomaly(values, current)

        assert result is not None
        assert result["anomaly"] is True
        assert result["direction"] == "drop"
        assert result["z_score"] < -2.5

    def test_fewer_than_7_returns_none(self):
        """Returns None with fewer than 7 data points."""
        values = [100, 102, 98, 101, 99]
        result = detect_metric_anomaly(values, 200)
        assert result is None

    def test_mad_zero_returns_none(self):
        """Returns None when all values are identical (MAD=0)."""
        values = [100, 100, 100, 100, 100, 100, 100]
        result = detect_metric_anomaly(values, 200)
        assert result is None

    def test_normal_value_returns_none(self):
        """Returns None when value is within normal range."""
        values = [100, 102, 98, 101, 99, 103, 97]
        current = 101  # Normal value

        result = detect_metric_anomaly(values, current)
        assert result is None

    def test_high_severity_threshold(self):
        """High severity when |z| > 4."""
        values = [100, 102, 98, 101, 99, 103, 97]
        current = 500  # Extreme spike

        result = detect_metric_anomaly(values, current)

        assert result is not None
        assert result["severity"] == "high"


class TestDetectClientAnomalies:
    """Tests for detect_client_anomalies."""

    def test_detects_anomalies_with_sufficient_data(
        self, db_session, sample_client
    ):
        """Detects anomalies when enough metric data exists."""
        cid = sample_client.id
        today = date.today()

        # Create 8 normal values + 1 anomalous value for "likes"
        for i in range(8):
            _make_metric(
                db_session,
                cid,
                "likes",
                100 + (i % 3),
                today - timedelta(days=9 - i),
            )
        # Anomalous spike on the most recent day
        _make_metric(db_session, cid, "likes", 500, today)

        anomalies = detect_client_anomalies(db_session, cid)

        assert len(anomalies) >= 1
        likes_anomaly = next(
            (a for a in anomalies if a["metric_name"] == "likes"), None
        )
        assert likes_anomaly is not None
        assert likes_anomaly["direction"] == "spike"


# -- ICP comparison tests ------------------------------------------------------


class TestCompareAudienceToICP:
    """Tests for compare_audience_to_icp."""

    def test_matching_demographics(self):
        """Returns match percentages when demographics align."""
        actual = {
            "age": {"25-34": 40.0, "35-44": 30.0, "18-24": 20.0, "45-54": 10.0},
            "gender": {"F": 65.0, "M": 35.0},
            "city": {"Toronto": 30.0, "Hamilton": 20.0, "London": 15.0},
            "country": {"CA": 85.0, "US": 15.0},
        }

        target = {
            "personas": [
                {
                    "name": "Young Professional",
                    "age_range": "25-44",
                    "gender": "female",
                    "location": "Toronto",
                }
            ]
        }

        result = compare_audience_to_icp(actual, target)

        assert "personas" in result
        assert "Young Professional" in result["personas"]

        yp = result["personas"]["Young Professional"]
        # Age 25-34 (40%) + 35-44 (30%) = 70%
        assert yp["age_match_pct"] == 70.0
        # Female = 65%
        assert yp["gender_match_pct"] == 65.0
        # Toronto = 30%
        assert yp["location_match_pct"] == 30.0
        assert yp["overall_match_pct"] > 0
        assert result["overall_icp_fit"] > 0

    def test_empty_demographics_returns_zeros(self):
        """Returns zeros when demographics are empty."""
        result = compare_audience_to_icp({}, {"personas": [{"name": "Test"}]})

        assert result["overall_icp_fit"] == 0.0

    def test_no_personas_returns_empty(self):
        """Returns empty when no personas defined."""
        result = compare_audience_to_icp(
            {"age": {"25-34": 50}}, {"not_personas": True}
        )

        assert result["personas"] == {}
        assert result["overall_icp_fit"] == 0.0


# -- Share of voice tests ------------------------------------------------------


class TestComputeShareOfVoice:
    """Tests for compute_share_of_voice."""

    def test_with_competitor_data(self, db_session, sample_client):
        """Computes SOV correctly with competitor snapshots."""
        cid = sample_client.id
        today = date.today()

        # Create client engagement
        for i in range(5):
            _make_metric(
                db_session, cid, "likes", 50, today - timedelta(days=i)
            )

        # Create a published draft for post count
        _make_draft(db_session, cid, published_at=datetime(
            2026, 2, 15, 10, 0, tzinfo=timezone.utc
        ))

        # Create competitor
        comp = Competitor(
            client_id=cid,
            name="Rival Co",
            is_primary=1,
        )
        db_session.add(comp)
        db_session.flush()

        # Create competitor snapshot
        snap = CompetitorSnapshot(
            client_id=cid,
            competitor_id=comp.id,
            post_frequency_7d=5,
            avg_engagement_rate=0.03,
        )
        db_session.add(snap)
        db_session.flush()

        result = compute_share_of_voice(db_session, cid)

        assert "sov_score" in result
        assert 0 <= result["sov_score"] <= 1
        assert result["client_engagement"] > 0
        assert len(result["competitor_data"]) == 1
        assert result["competitor_data"][0]["name"] == "Rival Co"
        assert result["trend"] in ("up", "down", "stable")

    def test_no_competitors_returns_full_sov(self, db_session, sample_client):
        """Without competitors, client has 100% SOV."""
        cid = sample_client.id
        today = date.today()

        _make_metric(db_session, cid, "likes", 50, today)

        result = compute_share_of_voice(db_session, cid)

        # With engagement but no competitors, SOV should be 1.0
        assert result["sov_score"] == 1.0


# -- Briefing tests ------------------------------------------------------------


class TestGenerateMorningBrief:
    """Tests for generate_morning_brief."""

    def test_classifies_clients_correctly(self, db_session, sample_client):
        """Portfolio grid classifies clients as sage/amber/coral."""
        # Client with no anomalies should be sage
        settings = _mock_settings()

        result = generate_morning_brief(db_session, settings)

        assert "portfolio_grid" in result
        assert "summary_stats" in result
        assert result["summary_stats"]["total_clients"] >= 1

        # sample_client should be sage (no anomalies, no KPI data)
        grid_entry = next(
            (
                g
                for g in result["portfolio_grid"]
                if g["client_id"] == sample_client.id
            ),
            None,
        )
        assert grid_entry is not None
        assert grid_entry["status_color"] == "sage"

    def test_coral_classification_with_declining_engagement(
        self, db_session, sample_client
    ):
        """Client with declining engagement 3+ weeks is classified coral."""
        cid = sample_client.id

        # Create 4 weeks of declining engagement (most recent = lowest)
        # _is_engagement_declining uses ORDER BY week_end DESC, so:
        # snapshots[0] = most recent (4.0), snapshots[1] = 6.0, etc.
        # It checks snapshots[i] < snapshots[i+1] for consecutive decline
        base = date.today()
        for i in range(4):
            we = base - timedelta(weeks=i)
            ws = we - timedelta(days=6)
            kpi = KPISnapshot(
                client_id=cid,
                week_start=ws,
                week_end=we,
                engagement_rate=4.0 + i * 2,  # 4, 6, 8, 10 (ascending by age = declining over time)
            )
            db_session.add(kpi)
        db_session.flush()

        settings = _mock_settings()
        result = generate_morning_brief(db_session, settings)

        grid_entry = next(
            g for g in result["portfolio_grid"] if g["client_id"] == cid
        )
        assert grid_entry["status_color"] == "coral"


class TestGenerateTelegramDigest:
    """Tests for generate_telegram_digest."""

    def test_produces_three_groups(self, db_session, sample_client):
        """Always returns 3 message groups (attention, calibrating, cruising)."""
        result = generate_telegram_digest(db_session)

        assert len(result) == 3
        groups = [r["group"] for r in result]
        assert "attention" in groups
        assert "calibrating" in groups
        assert "cruising" in groups

    def test_sage_client_in_cruising(self, db_session, sample_client):
        """Client with no anomalies appears in cruising group."""
        result = generate_telegram_digest(db_session)

        cruising = next(r for r in result if r["group"] == "cruising")
        client_ids = [c["client_id"] for c in cruising["clients"]]
        assert sample_client.id in client_ids


# -- Helpers -------------------------------------------------------------------


def _mock_settings():
    """Create a minimal Settings-like object for briefing tests."""

    class MockSettings:
        operator_timezone = "America/Toronto"
        facebook_access_token = ""
        instagram_access_token = ""
        facebook_page_id = ""
        instagram_business_account_id = ""

    return MockSettings()
