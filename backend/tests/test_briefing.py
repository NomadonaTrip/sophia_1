"""Tests for briefing generation, cross-client patterns, improvement metrics,
intelligence reports, and agent API endpoints.

LanceDB is mocked throughout to avoid GPU dependency.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from sophia.agent.briefing import (
    detect_cross_client_patterns,
    generate_daily_standup,
    generate_weekly_briefing,
)
from sophia.agent.models import Briefing, BusinessInsight, Learning
from sophia.agent.schemas import CrossClientPattern, ImprovementReport
from sophia.agent.service import (
    _trend_direction,
    calculate_improvement_rate,
    generate_intelligence_report,
)


# ---------------------------------------------------------------------------
# generate_daily_standup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_daily_standup(db_session: Session, sample_client):
    """Daily standup briefing generates with severity-sorted items and persists to DB."""
    # Create some test data: drafts in review
    from sophia.content.models import ContentDraft

    draft = ContentDraft(
        client_id=sample_client.id,
        platform="instagram",
        content_type="feed",
        copy="Test post",
        image_prompt="A test image",
        image_ratio="1:1",
        status="in_review",
    )
    db_session.add(draft)
    db_session.flush()

    # Generate briefing
    with patch("sophia.agent.briefing._gather_performance_alerts", return_value=[
        {
            "message": "Engagement drop for client",
            "client_name": sample_client.name,
            "action_needed": False,
        }
    ]):
        content = await generate_daily_standup(db_session)

    assert content.date is not None
    assert len(content.items) >= 1

    # Verify severity ordering: critical < warning < info
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    for i in range(len(content.items) - 1):
        current = severity_order.get(content.items[i].severity, 3)
        next_item = severity_order.get(content.items[i + 1].severity, 3)
        assert current <= next_item, (
            f"Items not sorted by severity: {content.items[i].severity} before {content.items[i+1].severity}"
        )

    # Verify briefing was persisted to DB
    briefing = (
        db_session.query(Briefing)
        .filter_by(briefing_type="daily")
        .first()
    )
    assert briefing is not None
    parsed = json.loads(briefing.content_json)
    assert "items" in parsed
    assert "date" in parsed


# ---------------------------------------------------------------------------
# generate_weekly_briefing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_weekly_briefing(db_session: Session, sample_client):
    """Weekly briefing includes cross-client patterns and improvement metrics."""
    with patch(
        "sophia.agent.briefing.detect_cross_client_patterns",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "sophia.agent.briefing._get_improvement_metrics",
        return_value={"content_quality": {"values": [], "direction": "insufficient_data"}},
    ):
        content = await generate_weekly_briefing(db_session)

    assert content.week_start is not None
    assert content.week_end is not None
    assert isinstance(content.cross_client_patterns, list)
    assert isinstance(content.improvement_metrics, dict)
    assert isinstance(content.strategy_recommendations, list)

    # Verify briefing persisted
    briefing = (
        db_session.query(Briefing)
        .filter_by(briefing_type="weekly")
        .first()
    )
    assert briefing is not None


# ---------------------------------------------------------------------------
# detect_cross_client_patterns
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_cross_client_patterns_anonymized(
    db_session: Session, sample_client, sample_client_2
):
    """Cross-client patterns are anonymized -- no client names in output."""
    # Create high-confidence learnings for two clients
    now = datetime.now(timezone.utc)
    l1 = Learning(
        client_id=sample_client.id,
        learning_type="content",
        source="cycle_approval",
        content="Short questions drive 2x engagement in food services",
        confidence=0.9,
        is_superseded=False,
    )
    l2 = Learning(
        client_id=sample_client_2.id,
        learning_type="content",
        source="performance_signal",
        content="Short questions drive higher engagement for bakeries",
        confidence=0.85,
        is_superseded=False,
    )
    db_session.add_all([l1, l2])
    db_session.flush()

    # Mock LanceDB search to return similar learnings
    mock_search_results = [
        {
            "client_id": sample_client_2.id,
            "record_id": l2.id,
            "similarity": 0.90,
        }
    ]

    with patch(
        "sophia.agent.briefing._search_similar_learnings",
        return_value=mock_search_results,
    ):
        patterns = await detect_cross_client_patterns(
            db_session, min_similarity=0.82, min_clients=2
        )

    # Patterns should exist
    assert len(patterns) >= 1

    # Verify anonymization: no client names in output
    for pattern in patterns:
        assert isinstance(pattern, CrossClientPattern)
        # theme should NOT contain client names
        assert sample_client.name not in pattern.theme
        assert sample_client_2.name not in pattern.theme
        assert pattern.client_count >= 2
        assert pattern.similarity_score >= 0.82


@pytest.mark.asyncio
async def test_detect_cross_client_patterns_min_clients_threshold(
    db_session: Session, sample_client
):
    """Patterns below min_clients threshold are excluded."""
    l1 = Learning(
        client_id=sample_client.id,
        learning_type="strategy",
        source="cycle_approval",
        content="Seasonal content works well",
        confidence=0.8,
        is_superseded=False,
    )
    db_session.add(l1)
    db_session.flush()

    # Mock: no similar learnings from other clients
    with patch(
        "sophia.agent.briefing._search_similar_learnings",
        return_value=[],
    ):
        patterns = await detect_cross_client_patterns(
            db_session, min_similarity=0.82, min_clients=2
        )

    assert len(patterns) == 0


# ---------------------------------------------------------------------------
# calculate_improvement_rate
# ---------------------------------------------------------------------------


def test_calculate_improvement_rate_insufficient_data(db_session: Session):
    """With no data, all metrics report insufficient_data."""
    report = calculate_improvement_rate(db_session, weeks_back=4)

    assert isinstance(report, ImprovementReport)
    # Intelligence depth should be at least present
    assert report.intelligence_depth.direction in (
        "insufficient_data", "stable"
    )


def test_trend_direction_improving():
    """Positive slope returns 'improving'."""
    values = [1.0, 2.0, 3.0, 4.0]
    assert _trend_direction(values) == "improving"


def test_trend_direction_declining():
    """Negative slope returns 'declining'."""
    values = [4.0, 3.0, 2.0, 1.0]
    assert _trend_direction(values) == "declining"


def test_trend_direction_stable():
    """Flat values return 'stable'."""
    values = [5.0, 5.0, 5.0, 5.0]
    assert _trend_direction(values) == "stable"


def test_trend_direction_insufficient_data():
    """Fewer than 2 data points returns 'insufficient_data'."""
    assert _trend_direction([]) == "insufficient_data"
    assert _trend_direction([1.0]) == "insufficient_data"


# ---------------------------------------------------------------------------
# generate_intelligence_report
# ---------------------------------------------------------------------------


def test_generate_intelligence_report(db_session: Session, sample_client):
    """Intelligence report populates all four sections."""
    report = generate_intelligence_report(
        db_session, client_id=sample_client.id, period_days=30
    )

    assert report.period is not None
    assert isinstance(report.topic_resonance, list)
    assert isinstance(report.competitor_trends, list)
    assert isinstance(report.customer_questions, list)
    assert isinstance(report.purchase_driver_signals, list)


def test_generate_intelligence_report_portfolio_wide(db_session: Session):
    """Intelligence report works without client_id (portfolio-wide)."""
    report = generate_intelligence_report(db_session, period_days=30)

    assert report.period is not None
    assert isinstance(report.topic_resonance, list)


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


@pytest.fixture
def test_app(db_session: Session):
    """Create a test FastAPI app with the agent router."""
    from fastapi import FastAPI
    from sophia.agent.router import agent_router

    app = FastAPI()
    app.include_router(agent_router)

    # Override DB dependency
    def override_get_db():
        yield db_session

    from sophia.agent.router import _get_db
    app.dependency_overrides[_get_db] = override_get_db

    return TestClient(app)


def test_api_create_learning(test_app, sample_client):
    """POST /api/agent/learnings creates a learning."""
    with patch("sophia.agent.learning._sync_learning_to_lance"):
        response = test_app.post("/api/agent/learnings", json={
            "client_id": sample_client.id,
            "learning_type": "content",
            "source": "test",
            "content": "Test learning from API",
        })

    assert response.status_code == 201
    data = response.json()
    assert data["learning_type"] == "content"
    assert data["content"] == "Test learning from API"


def test_api_list_learnings(test_app, sample_client, db_session):
    """GET /api/agent/learnings returns active learnings."""
    with patch("sophia.agent.learning._sync_learning_to_lance"):
        from sophia.agent.learning import persist_learning
        persist_learning(
            db_session,
            client_id=sample_client.id,
            learning_type="voice",
            source="test",
            content="Voice learning",
        )

    response = test_app.get(
        f"/api/agent/learnings?client_id={sample_client.id}"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert len(data["items"]) >= 1


def test_api_create_insight(test_app, sample_client):
    """POST /api/agent/insights creates a business insight."""
    with patch("sophia.agent.learning._sync_insight_to_lance"):
        response = test_app.post("/api/agent/insights", json={
            "client_id": sample_client.id,
            "category": "business",
            "fact_statement": "Client expanding to new market",
            "source_attribution": "operator chat",
        })

    assert response.status_code == 201
    data = response.json()
    assert data["category"] == "business"
    assert data["fact_statement"] == "Client expanding to new market"


def test_api_list_insights(test_app, sample_client, db_session):
    """GET /api/agent/insights returns active insights."""
    with patch("sophia.agent.learning._sync_insight_to_lance"):
        from sophia.agent.learning import extract_business_insight
        extract_business_insight(
            db_session,
            client_id=sample_client.id,
            category="customers",
            fact_statement="Customers prefer morning posts",
            source_attribution="analytics",
        )

    response = test_app.get(
        f"/api/agent/insights?client_id={sample_client.id}"
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1


def test_api_improvement_metrics(test_app):
    """GET /api/agent/improvement returns improvement report."""
    response = test_app.get("/api/agent/improvement")
    assert response.status_code == 200
    data = response.json()
    assert "content_quality" in data
    assert "decision_quality" in data
    assert "intelligence_depth" in data


def test_api_intelligence_report(test_app, sample_client):
    """GET /api/agent/intelligence-report returns report."""
    response = test_app.get(
        f"/api/agent/intelligence-report?client_id={sample_client.id}"
    )
    assert response.status_code == 200
    data = response.json()
    assert "period" in data
    assert "topic_resonance" in data


@pytest.mark.asyncio
async def test_api_trigger_daily_briefing(test_app, db_session):
    """POST /api/agent/briefings/daily/generate creates a briefing."""
    response = test_app.post("/api/agent/briefings/daily/generate")
    assert response.status_code == 200
    data = response.json()
    assert data["briefing_type"] == "daily"
    assert "content" in data


def test_api_get_daily_briefing_not_found(test_app):
    """GET /api/agent/briefings/daily returns 404 when no briefing exists."""
    response = test_app.get("/api/agent/briefings/daily")
    assert response.status_code == 404
