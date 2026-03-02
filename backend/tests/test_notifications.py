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
from sophia.notifications.service import (
    approve_value_signal,
    dismiss_value_signal,
    get_notification_history,
    process_notification_queue,
)


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

    def test_send_performance_report_calls_resend(self):
        """send_performance_report calls resend.Emails.send with correct params."""
        import asyncio
        import resend as resend_module
        from sophia.notifications.email import send_performance_report

        mock_send = MagicMock(return_value={"id": "re_test123"})

        with patch.object(resend_module.Emails, "send", mock_send), \
             patch("sophia.config.get_settings") as mock_settings:
            settings = MagicMock()
            settings.resend_api_key = "test_key"
            settings.notification_from_email = "test@example.com"
            settings.notification_from_name = "Test Sender"
            mock_settings.return_value = settings

            result = asyncio.run(
                send_performance_report(
                    client_email="client@example.com",
                    client_name="Test Client",
                    metrics={"engagement_rate": 0.05},
                    period="Test Period",
                )
            )

        assert result == "re_test123"
        mock_send.assert_called_once()
        call_params = mock_send.call_args[0][0]
        assert call_params["to"] == ["client@example.com"]
        assert "Test Period" in call_params["subject"]

    def test_send_performance_report_failure_returns_none(self):
        """send_performance_report returns None on Resend failure."""
        import asyncio
        import resend as resend_module
        from sophia.notifications.email import send_performance_report

        mock_send = MagicMock(side_effect=Exception("API error"))

        with patch.object(resend_module.Emails, "send", mock_send), \
             patch("sophia.config.get_settings") as mock_settings:
            settings = MagicMock()
            settings.resend_api_key = "test_key"
            settings.notification_from_email = "test@example.com"
            settings.notification_from_name = "Test Sender"
            mock_settings.return_value = settings

            result = asyncio.run(
                send_performance_report(
                    client_email="client@example.com",
                    client_name="Test",
                    metrics={},
                    period="Test",
                )
            )

        assert result is None


# ---------------------------------------------------------------------------
# Service tests
# ---------------------------------------------------------------------------


class TestService:
    """Tests for notification service logic."""

    @pytest.mark.asyncio
    @patch("sophia.notifications.email.send_performance_report", new_callable=AsyncMock)
    async def test_process_queue_sends_for_active_client(
        self, mock_send, db_session, sample_client
    ):
        """Queue processes clients with active preferences and sends email."""
        mock_send.return_value = "re_queue_test"

        pref = NotificationPreference(
            client_id=sample_client.id,
            frequency="weekly",
            email_address="dana@example.com",
            is_active=True,
        )
        db_session.add(pref)
        db_session.flush()

        result = await process_notification_queue(db_session)

        assert result["clients_processed"] >= 1
        assert result["emails_sent"] >= 1
        mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_queue_skips_client_without_preferences(
        self, db_session, sample_client
    ):
        """Queue skips clients without notification preferences entirely."""
        # No preferences created for sample_client
        result = await process_notification_queue(db_session)

        assert result["clients_processed"] == 0
        assert result["emails_sent"] == 0

    @pytest.mark.asyncio
    @patch("sophia.notifications.email.send_performance_report", new_callable=AsyncMock)
    async def test_frequency_enforcement_not_due(
        self, mock_send, db_session, sample_client
    ):
        """Queue does NOT send if last notification was recent (frequency not due)."""
        pref = NotificationPreference(
            client_id=sample_client.id,
            frequency="weekly",
            email_address="dana@example.com",
            is_active=True,
        )
        db_session.add(pref)
        db_session.flush()

        # Add recent notification log (3 days ago -- not due for weekly)
        log = NotificationLog(
            client_id=sample_client.id,
            notification_type="performance_report",
            subject="Recent report",
            status="sent",
            sent_at=datetime.now() - timedelta(days=3),
            resend_message_id="re_recent",
        )
        db_session.add(log)
        db_session.flush()

        result = await process_notification_queue(db_session)

        assert result["clients_processed"] >= 1
        assert result["emails_sent"] == 0
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    @patch("sophia.notifications.email.send_performance_report", new_callable=AsyncMock)
    async def test_frequency_enforcement_due(
        self, mock_send, db_session, sample_client
    ):
        """Queue sends when enough time has elapsed since last notification."""
        mock_send.return_value = "re_due_test"

        pref = NotificationPreference(
            client_id=sample_client.id,
            frequency="weekly",
            email_address="dana@example.com",
            is_active=True,
        )
        db_session.add(pref)
        db_session.flush()

        # Add old notification log (10 days ago -- due for weekly)
        log = NotificationLog(
            client_id=sample_client.id,
            notification_type="performance_report",
            subject="Old report",
            status="sent",
            sent_at=datetime.now() - timedelta(days=10),
            resend_message_id="re_old",
        )
        db_session.add(log)
        db_session.flush()

        result = await process_notification_queue(db_session)

        assert result["emails_sent"] >= 1
        mock_send.assert_called_once()

    @pytest.mark.asyncio
    @patch("sophia.notifications.email.send_value_signal_email", new_callable=AsyncMock)
    async def test_approve_value_signal_sends_email(
        self, mock_send, db_session, sample_client
    ):
        """Approving a value signal sends the email and updates status to 'sent'."""
        mock_send.return_value = "re_signal_test"

        # Create preference so email can be sent
        pref = NotificationPreference(
            client_id=sample_client.id,
            frequency="weekly",
            email_address="dana@example.com",
            is_active=True,
        )
        db_session.add(pref)
        db_session.flush()

        signal = ValueSignal(
            client_id=sample_client.id,
            signal_type="enquiry_driver",
            headline="12 enquiries from spring prep post!",
            details="Great results.",
            metric_value=12.0,
            metric_baseline=4.0,
            status="pending",
        )
        db_session.add(signal)
        db_session.flush()

        result = await approve_value_signal(db_session, signal.id)

        assert result is not None
        assert result.status == "sent"
        assert result.sent_at is not None
        assert result.approved_at is not None
        mock_send.assert_called_once()

    def test_dismiss_value_signal(self, db_session, sample_client):
        """Dismissing a value signal sets status to 'dismissed' with no email."""
        signal = ValueSignal(
            client_id=sample_client.id,
            signal_type="audience_growth",
            headline="Growth!",
            details="Details.",
            status="pending",
        )
        db_session.add(signal)
        db_session.flush()

        result = dismiss_value_signal(db_session, signal.id)

        assert result is not None
        assert result.status == "dismissed"
        assert result.sent_at is None

    def test_dismiss_non_pending_signal_returns_none(self, db_session, sample_client):
        """Cannot dismiss a signal that is not pending."""
        signal = ValueSignal(
            client_id=sample_client.id,
            signal_type="audience_growth",
            headline="Already sent",
            details="Details.",
            status="sent",
        )
        db_session.add(signal)
        db_session.flush()

        result = dismiss_value_signal(db_session, signal.id)
        assert result is None

    def test_get_notification_history(self, db_session, sample_client):
        """Notification history returns logs ordered by sent_at desc."""
        for i in range(3):
            log = NotificationLog(
                client_id=sample_client.id,
                notification_type="performance_report",
                subject=f"Report {i}",
                status="sent",
                sent_at=datetime.now() - timedelta(days=i),
                resend_message_id=f"re_{i}",
            )
            db_session.add(log)
        db_session.flush()

        history = get_notification_history(db_session, client_id=sample_client.id)

        assert len(history) == 3
        # Most recent first
        assert history[0].subject == "Report 0"
        assert history[2].subject == "Report 2"

    def test_get_notification_history_with_limit(self, db_session, sample_client):
        """History respects limit parameter."""
        for i in range(5):
            log = NotificationLog(
                client_id=sample_client.id,
                notification_type="performance_report",
                subject=f"Report {i}",
                status="sent",
                sent_at=datetime.now() - timedelta(days=i),
            )
            db_session.add(log)
        db_session.flush()

        history = get_notification_history(db_session, client_id=sample_client.id, limit=2)
        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_approve_nonexistent_signal_returns_none(self, db_session):
        """Approving a nonexistent signal returns None."""
        result = await approve_value_signal(db_session, 9999)
        assert result is None

    @pytest.mark.asyncio
    async def test_approve_non_pending_signal_returns_none(self, db_session, sample_client):
        """Cannot approve a signal that is not in pending state."""
        signal = ValueSignal(
            client_id=sample_client.id,
            signal_type="audience_growth",
            headline="Already dismissed",
            details="Details.",
            status="dismissed",
        )
        db_session.add(signal)
        db_session.flush()

        result = await approve_value_signal(db_session, signal.id)
        assert result is None


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestAPI:
    """Tests for notification REST API endpoints."""

    def test_create_preferences(self, db_session, sample_client):
        """POST /preferences creates notification preferences."""
        from fastapi.testclient import TestClient
        from sophia.notifications.router import notification_router, _get_db
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(notification_router)

        def override_get_db():
            yield db_session

        app.dependency_overrides[_get_db] = override_get_db

        client = TestClient(app)
        resp = client.post("/api/notifications/preferences", json={
            "client_id": sample_client.id,
            "email_address": "test@example.com",
            "frequency": "weekly",
        })

        assert resp.status_code == 201
        data = resp.json()
        assert data["client_id"] == sample_client.id
        assert data["frequency"] == "weekly"
        assert data["is_active"] is True

    def test_get_preferences(self, db_session, sample_client):
        """GET /preferences/{client_id} returns existing preferences."""
        from fastapi.testclient import TestClient
        from sophia.notifications.router import notification_router, _get_db
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(notification_router)

        def override_get_db():
            yield db_session

        app.dependency_overrides[_get_db] = override_get_db

        # Create preference first
        pref = NotificationPreference(
            client_id=sample_client.id,
            frequency="monthly",
            email_address="get@example.com",
        )
        db_session.add(pref)
        db_session.flush()

        client = TestClient(app)
        resp = client.get(f"/api/notifications/preferences/{sample_client.id}")

        assert resp.status_code == 200
        assert resp.json()["email_address"] == "get@example.com"

    def test_get_preferences_404(self, db_session):
        """GET /preferences/{client_id} returns 404 if no preferences."""
        from fastapi.testclient import TestClient
        from sophia.notifications.router import notification_router, _get_db
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(notification_router)

        def override_get_db():
            yield db_session

        app.dependency_overrides[_get_db] = override_get_db

        client = TestClient(app)
        resp = client.get("/api/notifications/preferences/99999")

        assert resp.status_code == 404

    def test_update_preferences(self, db_session, sample_client):
        """PUT /preferences/{client_id} updates existing preferences."""
        from fastapi.testclient import TestClient
        from sophia.notifications.router import notification_router, _get_db
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(notification_router)

        def override_get_db():
            yield db_session

        app.dependency_overrides[_get_db] = override_get_db

        pref = NotificationPreference(
            client_id=sample_client.id,
            frequency="monthly",
            email_address="old@example.com",
        )
        db_session.add(pref)
        db_session.flush()

        client = TestClient(app)
        resp = client.put(f"/api/notifications/preferences/{sample_client.id}", json={
            "frequency": "weekly",
            "email_address": "new@example.com",
        })

        assert resp.status_code == 200
        assert resp.json()["frequency"] == "weekly"
        assert resp.json()["email_address"] == "new@example.com"

    def test_deactivate_preferences(self, db_session, sample_client):
        """DELETE /preferences/{client_id} sets is_active=False."""
        from fastapi.testclient import TestClient
        from sophia.notifications.router import notification_router, _get_db
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(notification_router)

        def override_get_db():
            yield db_session

        app.dependency_overrides[_get_db] = override_get_db

        pref = NotificationPreference(
            client_id=sample_client.id,
            frequency="weekly",
            email_address="delete@example.com",
            is_active=True,
        )
        db_session.add(pref)
        db_session.flush()

        client = TestClient(app)
        resp = client.delete(f"/api/notifications/preferences/{sample_client.id}")

        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    def test_notification_history(self, db_session, sample_client):
        """GET /history returns notification history with counts."""
        from fastapi.testclient import TestClient
        from sophia.notifications.router import notification_router, _get_db
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(notification_router)

        def override_get_db():
            yield db_session

        app.dependency_overrides[_get_db] = override_get_db

        for status in ["sent", "sent", "failed"]:
            log = NotificationLog(
                client_id=sample_client.id,
                notification_type="performance_report",
                subject="Report",
                status=status,
                sent_at=datetime.now(),
            )
            db_session.add(log)
        db_session.flush()

        client = TestClient(app)
        resp = client.get(
            f"/api/notifications/history?client_id={sample_client.id}"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert data["sent_count"] == 2
        assert data["failed_count"] == 1

    def test_list_value_signals(self, db_session, sample_client):
        """GET /value-signals returns signals with counts."""
        from fastapi.testclient import TestClient
        from sophia.notifications.router import notification_router, _get_db
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(notification_router)

        def override_get_db():
            yield db_session

        app.dependency_overrides[_get_db] = override_get_db

        for status in ["pending", "pending", "sent"]:
            signal = ValueSignal(
                client_id=sample_client.id,
                signal_type="enquiry_driver",
                headline="Test",
                details="Details",
                status=status,
            )
            db_session.add(signal)
        db_session.flush()

        client = TestClient(app)
        resp = client.get(
            f"/api/notifications/value-signals?client_id={sample_client.id}"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 3
        assert data["pending_count"] == 2
        assert data["sent_count"] == 1

    def test_dismiss_signal_endpoint(self, db_session, sample_client):
        """POST /value-signals/{id}/dismiss dismisses a pending signal."""
        from fastapi.testclient import TestClient
        from sophia.notifications.router import notification_router, _get_db
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(notification_router)

        def override_get_db():
            yield db_session

        app.dependency_overrides[_get_db] = override_get_db

        signal = ValueSignal(
            client_id=sample_client.id,
            signal_type="audience_growth",
            headline="Dismiss me",
            details="Details",
            status="pending",
        )
        db_session.add(signal)
        db_session.flush()

        client = TestClient(app)
        resp = client.post(f"/api/notifications/value-signals/{signal.id}/dismiss")

        assert resp.status_code == 200
        assert resp.json()["status"] == "dismissed"

    def test_manual_send_without_preferences_404(self, db_session, sample_client):
        """POST /send-report/{client_id} returns 404 without preferences."""
        from fastapi.testclient import TestClient
        from sophia.notifications.router import notification_router, _get_db
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(notification_router)

        def override_get_db():
            yield db_session

        app.dependency_overrides[_get_db] = override_get_db

        client = TestClient(app)
        resp = client.post(f"/api/notifications/send-report/{sample_client.id}")

        assert resp.status_code == 404

    def test_create_duplicate_preferences_409(self, db_session, sample_client):
        """POST /preferences returns 409 for duplicate client preferences."""
        from fastapi.testclient import TestClient
        from sophia.notifications.router import notification_router, _get_db
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(notification_router)

        def override_get_db():
            yield db_session

        app.dependency_overrides[_get_db] = override_get_db

        pref = NotificationPreference(
            client_id=sample_client.id,
            frequency="weekly",
            email_address="dup@example.com",
        )
        db_session.add(pref)
        db_session.flush()

        client = TestClient(app)
        resp = client.post("/api/notifications/preferences", json={
            "client_id": sample_client.id,
            "email_address": "dup2@example.com",
            "frequency": "monthly",
        })

        assert resp.status_code == 409
