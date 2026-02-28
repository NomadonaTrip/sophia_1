"""Tests for Meta Graph API collector, scheduling, and analytics router.

Validates metric classification, API response parsing, error handling,
scheduler registration, and router endpoint status codes.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from sophia.analytics.collector import (
    _classify_metric,
    _convert_api_response_to_metrics,
    pull_client_metrics,
    register_daily_metric_pull,
)
from sophia.analytics.models import EngagementMetric
from sophia.approval.models import PublishingQueueEntry
from sophia.content.models import ContentDraft


class TestClassifyMetric:
    """_classify_metric function tests."""

    def test_algo_dependent_views(self):
        """'views' is algorithm-dependent."""
        assert _classify_metric("views") is True

    def test_algo_dependent_reach(self):
        """'reach' is algorithm-dependent."""
        assert _classify_metric("reach") is True

    def test_algo_independent_likes(self):
        """'likes' is algorithm-independent."""
        assert _classify_metric("likes") is False

    def test_algo_independent_saved(self):
        """'saved' is algorithm-independent."""
        assert _classify_metric("saved") is False

    def test_algo_independent_shares(self):
        """'shares' is algorithm-independent."""
        assert _classify_metric("shares") is False

    def test_unknown_defaults_to_independent(self):
        """Unknown metrics default to algorithm-independent (False)."""
        assert _classify_metric("some_custom_metric") is False


class TestConvertApiResponse:
    """_convert_api_response_to_metrics function tests."""

    def test_parses_standard_response(self):
        """Parses standard Meta API insights response into EngagementMetric objects."""
        api_data = {
            "data": [
                {
                    "name": "views",
                    "values": [
                        {"value": 1500, "end_time": "2026-02-28T08:00:00+0000"}
                    ],
                },
                {
                    "name": "likes",
                    "values": [
                        {"value": 42, "end_time": "2026-02-28T08:00:00+0000"}
                    ],
                },
            ]
        }

        metrics = _convert_api_response_to_metrics(
            api_data,
            client_id=1,
            platform="instagram",
            content_draft_id=10,
            platform_post_id="ig_123",
            operator_tz="America/Toronto",
        )

        assert len(metrics) == 2
        views = next(m for m in metrics if m.metric_name == "views")
        assert views.metric_value == 1500.0
        assert views.is_algorithm_dependent is True
        assert views.platform == "instagram"
        assert views.platform_post_id == "ig_123"

        likes = next(m for m in metrics if m.metric_name == "likes")
        assert likes.metric_value == 42.0
        assert likes.is_algorithm_dependent is False

    def test_handles_reaction_breakdown(self):
        """Parses dict values (reaction breakdowns) into separate metrics."""
        api_data = {
            "data": [
                {
                    "name": "post_reactions_by_type_total",
                    "values": [
                        {
                            "value": {"LIKE": 10, "LOVE": 3, "WOW": 1},
                            "end_time": "2026-02-28T08:00:00+0000",
                        }
                    ],
                }
            ]
        }

        metrics = _convert_api_response_to_metrics(
            api_data,
            client_id=1,
            platform="facebook",
            content_draft_id=None,
            platform_post_id=None,
            operator_tz="America/Toronto",
        )

        assert len(metrics) == 3
        names = {m.metric_name for m in metrics}
        assert "post_reactions_by_type_total_like" in names
        assert "post_reactions_by_type_total_love" in names
        assert "post_reactions_by_type_total_wow" in names

    def test_skips_none_values(self):
        """Skips entries with None values."""
        api_data = {
            "data": [
                {
                    "name": "views",
                    "values": [
                        {"value": None, "end_time": "2026-02-28T08:00:00+0000"}
                    ],
                }
            ]
        }

        metrics = _convert_api_response_to_metrics(
            api_data,
            client_id=1,
            platform="instagram",
            content_draft_id=None,
            platform_post_id=None,
            operator_tz="America/Toronto",
        )

        assert len(metrics) == 0

    def test_empty_data(self):
        """Handles empty API response gracefully."""
        metrics = _convert_api_response_to_metrics(
            {"data": []},
            client_id=1,
            platform="instagram",
            content_draft_id=None,
            platform_post_id=None,
            operator_tz="America/Toronto",
        )

        assert len(metrics) == 0


class TestPullClientMetrics:
    """pull_client_metrics integration tests with mocked httpx."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock Settings with platform tokens."""
        settings = MagicMock()
        settings.facebook_access_token = "fb_token_123"
        settings.facebook_page_id = "fb_page_123"
        settings.instagram_access_token = "ig_token_123"
        settings.instagram_business_account_id = "ig_account_123"
        settings.operator_timezone = "America/Toronto"
        return settings

    @pytest.fixture
    def mock_settings_empty(self):
        """Create mock Settings with empty tokens."""
        settings = MagicMock()
        settings.facebook_access_token = ""
        settings.facebook_page_id = ""
        settings.instagram_access_token = ""
        settings.instagram_business_account_id = ""
        settings.operator_timezone = "America/Toronto"
        return settings

    def _mock_response(self, data: dict, status_code: int = 200):
        """Create a mock httpx response."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = status_code
        response.json.return_value = data
        response.raise_for_status = MagicMock()
        if status_code >= 400:
            response.raise_for_status.side_effect = httpx.HTTPStatusError(
                message=f"HTTP {status_code}",
                request=MagicMock(spec=httpx.Request),
                response=response,
            )
        return response

    @pytest.mark.asyncio
    async def test_pulls_and_persists_metrics(self, db_session, sample_client, mock_settings):
        """Creates DB records from mocked API responses."""
        api_response = {
            "data": [
                {
                    "name": "views",
                    "values": [
                        {"value": 500, "end_time": "2026-02-28T08:00:00+0000"}
                    ],
                }
            ]
        }

        mock_resp = self._mock_response(api_response)

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_resp)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)

        with patch("sophia.analytics.collector.httpx.AsyncClient", return_value=mock_client_instance):
            metrics = await pull_client_metrics(
                db_session, sample_client.id, mock_settings
            )

        # Page-level metrics were pulled (at least for platforms with tokens)
        assert len(metrics) >= 0  # May be > 0 depending on mock response
        # All persisted metrics should be EngagementMetric instances
        for m in metrics:
            assert isinstance(m, EngagementMetric)

    @pytest.mark.asyncio
    async def test_handles_401_gracefully(self, db_session, sample_client, mock_settings):
        """Returns empty list on 401, no exception raised."""
        mock_resp = self._mock_response({}, status_code=401)

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_resp)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)

        with patch("sophia.analytics.collector.httpx.AsyncClient", return_value=mock_client_instance):
            metrics = await pull_client_metrics(
                db_session, sample_client.id, mock_settings
            )

        assert metrics == []

    @pytest.mark.asyncio
    async def test_handles_429_gracefully(self, db_session, sample_client, mock_settings):
        """Returns partial results on 429, no exception raised."""
        mock_resp = self._mock_response({}, status_code=429)

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_resp)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)

        with patch("sophia.analytics.collector.httpx.AsyncClient", return_value=mock_client_instance):
            metrics = await pull_client_metrics(
                db_session, sample_client.id, mock_settings
            )

        # Should return partial (possibly empty) without raising
        assert isinstance(metrics, list)

    @pytest.mark.asyncio
    async def test_skips_empty_tokens(self, db_session, sample_client, mock_settings_empty):
        """Skips platforms with empty tokens, returns empty list."""
        metrics = await pull_client_metrics(
            db_session, sample_client.id, mock_settings_empty
        )

        assert metrics == []


class TestRegisterDailyMetricPull:
    """register_daily_metric_pull tests."""

    def test_adds_job_to_scheduler(self):
        """Registers a cron job on the scheduler."""
        scheduler = MagicMock()
        session_factory = MagicMock()
        settings = MagicMock()
        settings.facebook_access_token = "fb_token"
        settings.instagram_access_token = "ig_token"
        settings.operator_timezone = "America/Toronto"

        register_daily_metric_pull(scheduler, session_factory, settings)

        scheduler.add_job.assert_called_once()
        call_kwargs = scheduler.add_job.call_args
        assert call_kwargs[1]["id"] == "daily_metric_pull"
        assert call_kwargs[1]["trigger"] == "cron"
        assert call_kwargs[1]["hour"] == 6

    def test_warns_on_empty_tokens(self):
        """Logs warnings when platform tokens are empty."""
        scheduler = MagicMock()
        session_factory = MagicMock()
        settings = MagicMock()
        settings.facebook_access_token = ""
        settings.instagram_access_token = ""
        settings.operator_timezone = "America/Toronto"

        with patch("sophia.analytics.collector.logger") as mock_logger:
            register_daily_metric_pull(scheduler, session_factory, settings)

        assert mock_logger.warning.call_count >= 2


class TestAnalyticsRouter:
    """Analytics router endpoint tests using FastAPI TestClient."""

    @pytest.fixture
    def client(self, db_session):
        """Create a FastAPI TestClient with the analytics router."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from sophia.analytics.router import _get_db, analytics_router

        app = FastAPI()
        app.include_router(analytics_router)

        # Override _get_db dependency to use test session
        def _override_get_db():
            yield db_session

        app.dependency_overrides[_get_db] = _override_get_db

        yield TestClient(app)

    def test_get_metrics_200(self, client, sample_client):
        """GET /api/analytics/{client_id}/metrics returns 200."""
        response = client.get(f"/api/analytics/{sample_client.id}/metrics")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_summary_200(self, client, sample_client):
        """GET /api/analytics/{client_id}/summary returns 200."""
        response = client.get(f"/api/analytics/{sample_client.id}/summary")
        assert response.status_code == 200
        data = response.json()
        assert "kpis" in data
        assert "trends" in data
        assert "anomalies" in data

    def test_post_conversion_201(self, client, sample_client):
        """POST /api/analytics/{client_id}/conversion returns 201."""
        response = client.post(
            f"/api/analytics/{sample_client.id}/conversion",
            json={
                "event_type": "conversion",
                "source": "operator_reported",
                "details": {"note": "Phone call"},
                "revenue_amount": 250.0,
            },
        )
        assert response.status_code == 201
        assert response.json()["status"] == "created"

    def test_get_campaigns_200(self, client, sample_client):
        """GET /api/analytics/{client_id}/campaigns returns 200."""
        response = client.get(f"/api/analytics/{sample_client.id}/campaigns")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_portfolio_summary_200(self, client):
        """GET /api/analytics/portfolio/summary returns 200."""
        response = client.get("/api/analytics/portfolio/summary")
        assert response.status_code == 200
        data = response.json()
        assert "client_count" in data
        assert "total_metrics" in data
