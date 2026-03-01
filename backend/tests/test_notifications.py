"""Tests for the notifications module: models, email rendering, service, and API.

Tests are organized by function:
- test_models: ORM model creation and constraints
- test_email_rendering: Jinja2 template rendering with premailer CSS inlining
- test_service: Notification queue, value signal detection, approval flow
- test_api: REST endpoint responses
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from sophia.notifications.models import (
    NotificationFrequency,
    NotificationLog,
    NotificationPreference,
    ValueSignal,
)
from sophia.notifications.email import render_email_template


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestModels:
    """Tests for notification ORM models."""

    def test_notification_preference_creation(self, db_session, sample_client):
        """NotificationPreference stores per-client email settings."""
        pref = NotificationPreference(
            client_id=sample_client.id,
            frequency="weekly",
            email_address="dana@example.com",
            engagement_threshold=0.05,
            include_metrics=True,
            include_comparisons=True,
            is_active=True,
        )
        db_session.add(pref)
        db_session.flush()

        assert pref.id is not None
        assert pref.client_id == sample_client.id
        assert pref.frequency == "weekly"
        assert pref.email_address == "dana@example.com"
        assert pref.engagement_threshold == 0.05
        assert pref.is_active is True

    def test_notification_preference_unique_client(self, db_session, sample_client):
        """Only one preference set per client (unique constraint)."""
        pref1 = NotificationPreference(
            client_id=sample_client.id,
            frequency="weekly",
            email_address="dana@example.com",
        )
        db_session.add(pref1)
        db_session.flush()

        pref2 = NotificationPreference(
            client_id=sample_client.id,
            frequency="monthly",
            email_address="dana2@example.com",
        )
        db_session.add(pref2)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_notification_log_creation(self, db_session, sample_client):
        """NotificationLog tracks sent emails with Resend message IDs."""
        log = NotificationLog(
            client_id=sample_client.id,
            notification_type="performance_report",
            subject="Your Content Performance Report - Week of Feb 17-23",
            resend_message_id="re_abc123",
            status="sent",
            sent_at=datetime.now(),
        )
        db_session.add(log)
        db_session.flush()

        assert log.id is not None
        assert log.resend_message_id == "re_abc123"
        assert log.status == "sent"

    def test_notification_log_failed(self, db_session, sample_client):
        """NotificationLog captures error messages on failure."""
        log = NotificationLog(
            client_id=sample_client.id,
            notification_type="performance_report",
            subject="Report",
            status="failed",
            sent_at=datetime.now(),
            error_message="Resend API rate limit exceeded",
        )
        db_session.add(log)
        db_session.flush()

        assert log.status == "failed"
        assert log.error_message == "Resend API rate limit exceeded"

    def test_value_signal_creation(self, db_session, sample_client):
        """ValueSignal stores detected wins with status 'pending'."""
        signal = ValueSignal(
            client_id=sample_client.id,
            signal_type="enquiry_driver",
            headline="Your spring prep post drove 12 enquiries",
            details="The post about spring lawn preparation was shared 45 times and generated direct messages from 12 potential customers.",
            metric_value=12.0,
            metric_baseline=4.0,
            status="pending",
        )
        db_session.add(signal)
        db_session.flush()

        assert signal.id is not None
        assert signal.status == "pending"
        assert signal.approved_at is None
        assert signal.sent_at is None

    def test_value_signal_approval_transition(self, db_session, sample_client):
        """ValueSignal transitions: pending -> approved -> sent."""
        signal = ValueSignal(
            client_id=sample_client.id,
            signal_type="engagement_milestone",
            headline="First post to exceed 5% engagement!",
            details="Your tutorial video reached a 6.2% engagement rate.",
            metric_value=0.062,
            metric_baseline=0.035,
            status="pending",
        )
        db_session.add(signal)
        db_session.flush()

        # Approve
        signal.status = "approved"
        signal.approved_at = datetime.now()
        db_session.flush()
        assert signal.status == "approved"
        assert signal.approved_at is not None

        # Mark sent
        signal.status = "sent"
        signal.sent_at = datetime.now()
        db_session.flush()
        assert signal.status == "sent"
        assert signal.sent_at is not None

    def test_value_signal_dismissal(self, db_session, sample_client):
        """ValueSignal can be dismissed (pending -> dismissed)."""
        signal = ValueSignal(
            client_id=sample_client.id,
            signal_type="audience_growth",
            headline="20% follower growth this week",
            details="Audience grew from 500 to 600 followers.",
            status="pending",
        )
        db_session.add(signal)
        db_session.flush()

        signal.status = "dismissed"
        db_session.flush()
        assert signal.status == "dismissed"
        assert signal.sent_at is None

    def test_notification_frequency_enum(self):
        """NotificationFrequency enum has expected values."""
        assert NotificationFrequency.weekly.value == "weekly"
        assert NotificationFrequency.biweekly.value == "biweekly"
        assert NotificationFrequency.monthly.value == "monthly"
        assert NotificationFrequency.disabled.value == "disabled"


# ---------------------------------------------------------------------------
# Email rendering tests
# ---------------------------------------------------------------------------


class TestEmailRendering:
    """Tests for Jinja2 template rendering with premailer CSS inlining."""

    def test_performance_template_renders(self):
        """Performance template renders with client name, metrics, and period."""
        html = render_email_template("performance.html", {
            "client_name": "Shane's Bakery",
            "period": "Week of Feb 17-23, 2026",
            "year": 2026,
            "metrics": {
                "engagement_rate": 0.045,
                "reach": 1200,
                "impressions": 3500,
                "follower_growth": 15,
            },
            "highlights": [
                "Valentine's Day cupcake post reached 450 people",
                "Sourdough tutorial saved 23 times",
            ],
            "comparisons": {
                "engagement_rate": 0.01,
                "reach": 0.15,
            },
        })

        assert "Shane's Bakery" in html
        assert "Week of Feb 17-23, 2026" in html
        assert "4.5%" in html  # engagement_rate rendered as percentage
        assert "1,200" in html  # reach formatted with comma
        assert "Valentine's Day cupcake" in html
        assert "Sourdough tutorial" in html

    def test_value_signal_template_renders(self):
        """Value signal template renders with headline, metric, and comparison."""
        html = render_email_template("value_signal.html", {
            "client_name": "Dana's Landscaping",
            "headline": "Your spring prep post drove 12 enquiries!",
            "details": "The post was shared 45 times across local community groups.",
            "metric_value": 12,
            "metric_baseline": 4,
            "comparison_text": "That's 3.0x your average",
            "year": 2026,
        })

        assert "Dana's Landscaping" in html
        assert "spring prep post drove 12 enquiries" in html
        assert "12" in html  # hero metric
        assert "3.0x your average" in html
        assert "shared 45 times" in html

    def test_css_inlining_applied(self):
        """premailer inlines CSS into style attributes."""
        html = render_email_template("performance.html", {
            "client_name": "Test",
            "period": "Test Period",
            "year": 2026,
            "metrics": {"engagement_rate": 0.05},
            "highlights": [],
            "comparisons": {},
        })

        # premailer should have inlined the CSS -- style= attributes present
        assert 'style="' in html

    def test_performance_template_extends_base(self):
        """Performance template inherits base layout (header, footer)."""
        html = render_email_template("performance.html", {
            "client_name": "Test",
            "period": "Test",
            "year": 2026,
            "metrics": {},
            "highlights": [],
            "comparisons": {},
        })

        assert "Sophia" in html  # header branding
        assert "Orban Forest" in html  # footer
        assert "Unsubscribe" in html  # CAN-SPAM compliance

    def test_value_signal_template_extends_base(self):
        """Value signal template inherits base layout (header, footer)."""
        html = render_email_template("value_signal.html", {
            "client_name": "Test",
            "headline": "Great news!",
            "details": "Details here.",
            "metric_value": None,
            "metric_baseline": None,
            "comparison_text": None,
            "year": 2026,
        })

        assert "Sophia" in html
        assert "Unsubscribe" in html

    def test_value_signal_without_metric(self):
        """Value signal template renders cleanly without metric data."""
        html = render_email_template("value_signal.html", {
            "client_name": "Test Client",
            "headline": "Great progress on your content!",
            "details": "Your audience engagement has been consistently improving.",
            "metric_value": None,
            "metric_baseline": None,
            "comparison_text": None,
            "year": 2026,
        })

        assert "Great progress" in html
        assert "Test Client" in html

    def test_performance_template_no_highlights(self):
        """Performance report renders cleanly without highlights section."""
        html = render_email_template("performance.html", {
            "client_name": "Minimal Client",
            "period": "February 2026",
            "year": 2026,
            "metrics": {"reach": 500},
            "highlights": [],
            "comparisons": {},
        })

        assert "Minimal Client" in html
        assert "500" in html
