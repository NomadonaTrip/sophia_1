"""Tests for the learning persistence service.

Tests learning CRUD, supersession chains, active learning retrieval,
business insight extraction, and intelligence retrieval with category
filtering. LanceDB write-through is mocked to avoid GPU dependency.
"""

from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from sophia.agent.learning import (
    extract_business_insight,
    get_active_learnings,
    get_client_intelligence,
    mark_superseded,
    persist_learning,
)
from sophia.agent.models import BusinessInsight, Learning


# ---------------------------------------------------------------------------
# persist_learning
# ---------------------------------------------------------------------------


@patch("sophia.agent.learning._sync_learning_to_lance")
def test_persist_learning_creates_record(mock_lance, db_session: Session, sample_client):
    """persist_learning creates a Learning record with correct fields."""
    learning = persist_learning(
        db_session,
        client_id=sample_client.id,
        learning_type="content",
        source="cycle_approval",
        content="Short-form questions get 2x engagement for this client",
        confidence=0.9,
    )

    assert learning.id is not None
    assert learning.client_id == sample_client.id
    assert learning.learning_type == "content"
    assert learning.source == "cycle_approval"
    assert learning.content == "Short-form questions get 2x engagement for this client"
    assert learning.confidence == 0.9
    assert learning.is_superseded is False
    assert learning.superseded_by_id is None

    # Verify it's in DB
    found = db_session.get(Learning, learning.id)
    assert found is not None
    assert found.content == learning.content

    # Verify LanceDB sync was called
    mock_lance.assert_called_once_with(learning)


# ---------------------------------------------------------------------------
# mark_superseded
# ---------------------------------------------------------------------------


@patch("sophia.agent.learning._sync_learning_to_lance")
def test_mark_superseded(mock_lance, db_session: Session, sample_client):
    """mark_superseded sets is_superseded=True and links to new learning."""
    old = persist_learning(
        db_session,
        client_id=sample_client.id,
        learning_type="content",
        source="cycle_approval",
        content="Listicles perform best",
        confidence=0.7,
    )
    new = persist_learning(
        db_session,
        client_id=sample_client.id,
        learning_type="content",
        source="performance_signal",
        content="Questions outperform listicles 2:1",
        confidence=0.85,
        supersedes_id=old.id,
    )

    # Refresh old learning from DB
    db_session.refresh(old)

    assert old.is_superseded is True
    assert old.superseded_by_id == new.id
    assert new.is_superseded is False


# ---------------------------------------------------------------------------
# get_active_learnings
# ---------------------------------------------------------------------------


@patch("sophia.agent.learning._sync_learning_to_lance")
def test_get_active_learnings_excludes_superseded(mock_lance, db_session: Session, sample_client):
    """get_active_learnings returns only non-superseded learnings."""
    l1 = persist_learning(
        db_session,
        client_id=sample_client.id,
        learning_type="content",
        source="cycle_approval",
        content="Learning 1",
    )
    l2 = persist_learning(
        db_session,
        client_id=sample_client.id,
        learning_type="voice",
        source="operator_chat",
        content="Learning 2",
    )
    l3 = persist_learning(
        db_session,
        client_id=sample_client.id,
        learning_type="content",
        source="performance_signal",
        content="Learning 3 (supersedes 1)",
        supersedes_id=l1.id,
    )

    active = get_active_learnings(db_session, sample_client.id)

    assert len(active) == 2
    active_ids = {a.id for a in active}
    assert l2.id in active_ids
    assert l3.id in active_ids
    assert l1.id not in active_ids

    # Verify ordering: most recent first
    assert active[0].id == l3.id


@patch("sophia.agent.learning._sync_learning_to_lance")
def test_get_active_learnings_type_filter(mock_lance, db_session: Session, sample_client):
    """get_active_learnings with type filter returns only matching types."""
    persist_learning(
        db_session,
        client_id=sample_client.id,
        learning_type="content",
        source="cycle_approval",
        content="Content learning",
    )
    persist_learning(
        db_session,
        client_id=sample_client.id,
        learning_type="voice",
        source="operator_chat",
        content="Voice learning",
    )
    persist_learning(
        db_session,
        client_id=sample_client.id,
        learning_type="research",
        source="web_scrape",
        content="Research learning",
    )

    content_only = get_active_learnings(
        db_session, sample_client.id, learning_type="content"
    )
    assert len(content_only) == 1
    assert content_only[0].learning_type == "content"

    voice_only = get_active_learnings(
        db_session, sample_client.id, learning_type="voice"
    )
    assert len(voice_only) == 1
    assert voice_only[0].learning_type == "voice"


# ---------------------------------------------------------------------------
# extract_business_insight
# ---------------------------------------------------------------------------


@patch("sophia.agent.learning._sync_insight_to_lance")
def test_extract_business_insight(mock_lance, db_session: Session, sample_client):
    """extract_business_insight creates a BusinessInsight with all fields."""
    insight = extract_business_insight(
        db_session,
        client_id=sample_client.id,
        category="business",
        fact_statement="Shane is expanding into commercial HVAC",
        source_attribution="operator conversation 2026-02-26",
        confidence=0.9,
    )

    assert insight.id is not None
    assert insight.client_id == sample_client.id
    assert insight.category == "business"
    assert insight.fact_statement == "Shane is expanding into commercial HVAC"
    assert insight.source_attribution == "operator conversation 2026-02-26"
    assert insight.confidence == 0.9
    assert insight.is_active is True

    # Verify in DB
    found = db_session.get(BusinessInsight, insight.id)
    assert found is not None
    assert found.fact_statement == insight.fact_statement

    mock_lance.assert_called_once_with(insight)


# ---------------------------------------------------------------------------
# get_client_intelligence
# ---------------------------------------------------------------------------


@patch("sophia.agent.learning._sync_insight_to_lance")
def test_get_client_intelligence(mock_lance, db_session: Session, sample_client):
    """get_client_intelligence retrieves insights with optional category filter."""
    extract_business_insight(
        db_session,
        client_id=sample_client.id,
        category="business",
        fact_statement="Expanding to new market",
        source_attribution="operator chat",
    )
    extract_business_insight(
        db_session,
        client_id=sample_client.id,
        category="competitors",
        fact_statement="Main competitor launched loyalty program",
        source_attribution="research finding",
    )
    extract_business_insight(
        db_session,
        client_id=sample_client.id,
        category="customers",
        fact_statement="Customers prefer booking online",
        source_attribution="survey data",
    )

    # All categories
    all_insights = get_client_intelligence(db_session, sample_client.id)
    assert len(all_insights) == 3

    # Filter by category
    business_only = get_client_intelligence(
        db_session, sample_client.id, category="business"
    )
    assert len(business_only) == 1
    assert business_only[0].category == "business"

    competitors_only = get_client_intelligence(
        db_session, sample_client.id, category="competitors"
    )
    assert len(competitors_only) == 1
    assert competitors_only[0].fact_statement == "Main competitor launched loyalty program"
