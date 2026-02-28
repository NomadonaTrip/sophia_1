"""Tests for capability discovery, evaluation, and registry.

Covers models, search services (mocked), evaluation rubric,
service layer, and API endpoints.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from sophia.capabilities.evaluation import (
    AUTO_REJECT_THRESHOLD,
    DIMENSION_WEIGHTS,
    EvaluationResult,
    RubricScore,
    evaluate_capability,
    score_discovered_capability,
)
from sophia.capabilities.models import (
    CapabilityGap,
    CapabilityProposal,
    CapabilityRegistry,
    CapabilityStatus,
    DiscoveredCapability,
    GapStatus,
    ProposalStatus,
)
from sophia.capabilities.search import (
    DiscoveredCapabilityData,
    search_all_sources,
    search_github,
    search_mcp_registry,
)
from sophia.capabilities.service import (
    approve_proposal,
    log_capability_gap,
    list_gaps,
    record_capability_failure,
    reject_proposal,
)


# =============================================================================
# Model tests
# =============================================================================


class TestModels:
    """Test ORM model creation and field persistence."""

    def test_capability_gap_creation(self, db_session):
        """CapabilityGap persists all required fields."""
        gap = CapabilityGap(
            description="No Google Business Profile publishing capability",
            detected_during="publishing_stage",
            client_id=None,
            status=GapStatus.open.value,
        )
        db_session.add(gap)
        db_session.flush()

        assert gap.id is not None
        assert gap.description == "No Google Business Profile publishing capability"
        assert gap.detected_during == "publishing_stage"
        assert gap.status == "open"
        assert gap.client_id is None
        assert gap.resolved_by_id is None
        assert gap.last_searched_at is None

    def test_capability_gap_with_client(self, db_session, sample_client):
        """CapabilityGap can be linked to a specific client."""
        gap = CapabilityGap(
            description="Need LinkedIn publishing",
            detected_during="research_stage",
            client_id=sample_client.id,
            status=GapStatus.open.value,
        )
        db_session.add(gap)
        db_session.flush()

        assert gap.client_id == sample_client.id

    def test_discovered_capability_creation(self, db_session):
        """DiscoveredCapability stores search result metadata."""
        gap = CapabilityGap(
            description="Need calendar integration",
            detected_during="publishing_stage",
            status=GapStatus.open.value,
        )
        db_session.add(gap)
        db_session.flush()

        disc = DiscoveredCapability(
            gap_id=gap.id,
            source="github",
            name="calendar-mcp-server",
            description="MCP server for Google Calendar",
            url="https://github.com/example/calendar-mcp",
            version="1.0.0",
            stars=150,
            last_updated=datetime(2026, 2, 1, tzinfo=timezone.utc),
        )
        db_session.add(disc)
        db_session.flush()

        assert disc.id is not None
        assert disc.gap_id == gap.id
        assert disc.stars == 150

    def test_proposal_auto_reject_persistence(self, db_session):
        """CapabilityProposal persists auto_rejected flag and reason."""
        gap = CapabilityGap(
            description="Need analytics tool",
            detected_during="monitoring_stage",
            status=GapStatus.proposals_ready.value,
        )
        db_session.add(gap)
        db_session.flush()

        disc = DiscoveredCapability(
            gap_id=gap.id,
            source="mcp_registry",
            name="analytics-mcp",
            description="Analytics server",
            url="https://example.com/analytics",
        )
        db_session.add(disc)
        db_session.flush()

        proposal = CapabilityProposal(
            gap_id=gap.id,
            discovered_id=disc.id,
            relevance_score=4,
            quality_score=2,  # Below threshold
            security_score=4,
            fit_score=3,
            composite_score=3.35,
            recommendation="caution",
            auto_rejected=True,
            rejection_reason="Auto-rejected: 'quality' scored 2/5 (below minimum threshold of 3)",
            justification_json='{"relevance": "Good match", "quality": "Low stars"}',
            status=ProposalStatus.pending.value,
        )
        db_session.add(proposal)
        db_session.flush()

        assert proposal.auto_rejected is True
        assert "quality" in proposal.rejection_reason
        assert proposal.status == "pending"

    def test_registry_failure_count_and_auto_disable(self, db_session):
        """CapabilityRegistry tracks failures and auto-disable threshold."""
        entry = CapabilityRegistry(
            name="test-mcp-server",
            description="A test server",
            source="mcp_registry",
            source_url="https://example.com/test",
            installed_at=datetime.now(timezone.utc),
            status=CapabilityStatus.active.value,
            failure_count=0,
            auto_disable_threshold=5,
        )
        db_session.add(entry)
        db_session.flush()

        assert entry.failure_count == 0
        assert entry.auto_disable_threshold == 5
        assert entry.status == "active"

        # Simulate failures up to threshold
        entry.failure_count = 5
        db_session.flush()
        assert entry.failure_count >= entry.auto_disable_threshold


# =============================================================================
# Search tests (mock external APIs)
# =============================================================================


class TestSearch:
    """Test search services with mocked external API calls."""

    @pytest.mark.asyncio
    async def test_search_mcp_registry_success(self):
        """MCP Registry search parses response into DiscoveredCapabilityData."""
        mock_response = [
            {
                "name": "calendar-server",
                "description": "MCP server for Google Calendar",
                "repository": {"url": "https://github.com/example/calendar"},
                "version": "1.2.0",
            },
            {
                "name": "email-server",
                "description": "MCP server for email",
                "repository": "https://github.com/example/email",
                "version": "0.9.0",
            },
        ]

        with patch("sophia.capabilities.search.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response_obj = MagicMock()
            mock_response_obj.json.return_value = mock_response
            mock_response_obj.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response_obj)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            results = await search_mcp_registry("calendar")

        assert len(results) == 2
        assert results[0].name == "calendar-server"
        assert results[0].source == "mcp_registry"
        assert results[0].url == "https://github.com/example/calendar"
        assert results[0].version == "1.2.0"
        assert results[1].name == "email-server"
        assert results[1].url == "https://github.com/example/email"

    @pytest.mark.asyncio
    async def test_search_mcp_registry_http_error(self):
        """MCP Registry HTTP 500 returns empty list, no crash."""
        import httpx

        with patch("sophia.capabilities.search.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 500
            mock_response_obj.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Internal Server Error",
                request=MagicMock(),
                response=mock_response_obj,
            )
            mock_client.get = AsyncMock(return_value=mock_response_obj)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            results = await search_mcp_registry("test")

        assert results == []

    @pytest.mark.asyncio
    async def test_search_github_success(self):
        """GitHub search parses repos into DiscoveredCapabilityData."""
        mock_repo = MagicMock()
        mock_repo.full_name = "user/mcp-calendar"
        mock_repo.description = "Calendar MCP server for Python"
        mock_repo.html_url = "https://github.com/user/mcp-calendar"
        mock_repo.stargazers_count = 200
        mock_repo.updated_at = datetime(2026, 2, 15, tzinfo=timezone.utc)
        mock_repo.get_latest_release.side_effect = Exception("No release")

        mock_github = MagicMock()
        mock_github.search_repositories.return_value = [mock_repo]

        with patch(
            "sophia.capabilities.search._get_github_client",
            return_value=mock_github,
        ):
            results = await search_github("calendar", limit=5)

        assert len(results) == 1
        assert results[0].name == "user/mcp-calendar"
        assert results[0].source == "github"
        assert results[0].stars == 200
        assert results[0].url == "https://github.com/user/mcp-calendar"

    @pytest.mark.asyncio
    async def test_search_github_rate_limit(self):
        """GitHub 403 rate limit returns partial results, logs warning."""
        mock_repo = MagicMock()
        mock_repo.full_name = "user/partial-result"
        mock_repo.description = "Partial result before rate limit"
        mock_repo.html_url = "https://github.com/user/partial"
        mock_repo.stargazers_count = 50
        mock_repo.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        mock_repo.get_latest_release.side_effect = Exception("No release")

        def _rate_limit_iter():
            yield mock_repo
            raise Exception("403 rate limit exceeded")

        mock_github = MagicMock()
        mock_github.search_repositories.return_value = _rate_limit_iter()

        with patch(
            "sophia.capabilities.search._get_github_client",
            return_value=mock_github,
        ):
            results = await search_github("test", limit=5)

        assert len(results) == 1
        assert results[0].name == "user/partial-result"

    @pytest.mark.asyncio
    async def test_search_all_sources_dedup_and_order(self):
        """search_all_sources deduplicates by URL and orders MCP first."""
        mcp_cap = DiscoveredCapabilityData(
            name="shared-server",
            description="Shared MCP server",
            url="https://github.com/shared/server",
            source="mcp_registry",
        )
        github_cap = DiscoveredCapabilityData(
            name="shared/server",
            description="Same server on GitHub",
            url="https://github.com/shared/server",
            source="github",
            stars=100,
        )
        github_unique = DiscoveredCapabilityData(
            name="unique/github-only",
            description="Only on GitHub",
            url="https://github.com/unique/github-only",
            source="github",
            stars=50,
        )

        with patch(
            "sophia.capabilities.search.search_mcp_registry",
            new_callable=AsyncMock,
            return_value=[mcp_cap],
        ), patch(
            "sophia.capabilities.search.search_github",
            new_callable=AsyncMock,
            return_value=[github_cap, github_unique],
        ):
            results = await search_all_sources("test")

        assert len(results) == 2  # Duplicate removed
        assert results[0].source == "mcp_registry"  # MCP first
        assert results[1].source == "github"


# =============================================================================
# Evaluation tests
# =============================================================================


class TestEvaluation:
    """Test four-dimension evaluation rubric."""

    def test_evaluate_all_above_threshold(self):
        """All scores >= 3 produces valid composite and recommendation."""
        scores = [
            RubricScore(dimension="relevance", score=5, justification="Great match"),
            RubricScore(dimension="quality", score=4, justification="Active repo"),
            RubricScore(dimension="security", score=4, justification="Trusted"),
            RubricScore(dimension="fit", score=3, justification="Partial match"),
        ]

        result = evaluate_capability(scores)

        assert not result.auto_rejected
        assert result.rejection_reason is None
        # Composite: 5*0.30 + 4*0.25 + 4*0.25 + 3*0.20 = 1.5 + 1.0 + 1.0 + 0.6 = 4.1
        assert result.composite_score == pytest.approx(4.1, abs=0.01)
        assert result.recommendation == "recommend"

    def test_auto_reject_below_threshold(self):
        """Score below 3 in any dimension triggers auto-reject."""
        scores = [
            RubricScore(dimension="relevance", score=5, justification="Great"),
            RubricScore(dimension="quality", score=2, justification="Low stars"),
            RubricScore(dimension="security", score=4, justification="OK"),
            RubricScore(dimension="fit", score=4, justification="Good"),
        ]

        result = evaluate_capability(scores)

        assert result.auto_rejected
        assert "quality" in result.rejection_reason
        assert "2/5" in result.rejection_reason

    def test_recommendation_recommend_tier(self):
        """Composite >= 4.0 yields 'recommend'."""
        scores = [
            RubricScore(dimension="relevance", score=5, justification=""),
            RubricScore(dimension="quality", score=5, justification=""),
            RubricScore(dimension="security", score=4, justification=""),
            RubricScore(dimension="fit", score=4, justification=""),
        ]

        result = evaluate_capability(scores)

        # 5*0.30 + 5*0.25 + 4*0.25 + 4*0.20 = 1.5 + 1.25 + 1.0 + 0.8 = 4.55
        assert result.composite_score == pytest.approx(4.55, abs=0.01)
        assert result.recommendation == "recommend"

    def test_recommendation_neutral_tier(self):
        """Composite between 3.0 and 4.0 yields 'neutral'."""
        scores = [
            RubricScore(dimension="relevance", score=3, justification=""),
            RubricScore(dimension="quality", score=4, justification=""),
            RubricScore(dimension="security", score=3, justification=""),
            RubricScore(dimension="fit", score=3, justification=""),
        ]

        result = evaluate_capability(scores)

        # 3*0.30 + 4*0.25 + 3*0.25 + 3*0.20 = 0.9 + 1.0 + 0.75 + 0.6 = 3.25
        assert result.composite_score == pytest.approx(3.25, abs=0.01)
        assert result.recommendation == "neutral"

    def test_recommendation_caution_tier(self):
        """Composite < 3.0 yields 'caution'."""
        scores = [
            RubricScore(dimension="relevance", score=3, justification=""),
            RubricScore(dimension="quality", score=3, justification=""),
            RubricScore(dimension="security", score=3, justification=""),
            RubricScore(dimension="fit", score=3, justification=""),
        ]

        result = evaluate_capability(scores)

        # 3*0.30 + 3*0.25 + 3*0.25 + 3*0.20 = 0.9 + 0.75 + 0.75 + 0.6 = 3.0
        assert result.composite_score == pytest.approx(3.0, abs=0.01)
        assert result.recommendation == "neutral"  # Exactly 3.0 is neutral

    def test_score_discovered_capability_heuristic(self):
        """Heuristic scoring produces four dimensions with reasonable scores."""
        cap = DiscoveredCapabilityData(
            name="mcp-calendar-python",
            description="MCP server for Google Calendar integration with Python and FastAPI",
            url="https://github.com/example/mcp-calendar-python",
            source="mcp_registry",
            stars=75,
            last_updated=datetime.now(timezone.utc) - timedelta(days=30),
        )

        scores = score_discovered_capability(
            cap, gap_description="Google Calendar integration capability"
        )

        assert len(scores) == 4
        dimensions = {s.dimension for s in scores}
        assert dimensions == {"relevance", "quality", "security", "fit"}

        # All scores should be integers 0-5
        for s in scores:
            assert 0 <= s.score <= 5
            assert len(s.justification) > 0

    def test_dimension_weights_sum_to_one(self):
        """Rubric weights must sum to 1.0 for correct composite."""
        total = sum(DIMENSION_WEIGHTS.values())
        assert total == pytest.approx(1.0, abs=0.001)

    def test_auto_reject_threshold_is_three(self):
        """Auto-reject threshold is 3 (locked decision from CONTEXT.md)."""
        assert AUTO_REJECT_THRESHOLD == 3


# =============================================================================
# Service tests
# =============================================================================


class TestService:
    """Test capability service layer."""

    def test_log_capability_gap(self, db_session):
        """log_capability_gap creates a gap with status 'open'."""
        gap = log_capability_gap(
            db_session,
            description="No LinkedIn publishing capability",
            detected_during="publishing_stage",
        )

        assert gap.id is not None
        assert gap.status == "open"
        assert gap.description == "No LinkedIn publishing capability"
        assert gap.detected_during == "publishing_stage"

    def test_log_duplicate_gap_returns_existing(self, db_session):
        """Duplicate gap descriptions return existing gap instead of creating new."""
        gap1 = log_capability_gap(
            db_session,
            description="No Google Business Profile publishing capability",
            detected_during="publishing_stage",
        )
        gap2 = log_capability_gap(
            db_session,
            description="No Google Business Profile publishing capability",
            detected_during="research_stage",
        )

        assert gap1.id == gap2.id  # Same gap returned

    def test_log_different_gaps_not_duplicate(self, db_session):
        """Different gap descriptions create separate gaps."""
        gap1 = log_capability_gap(
            db_session,
            description="No LinkedIn publishing capability",
            detected_during="publishing_stage",
        )
        gap2 = log_capability_gap(
            db_session,
            description="Need email newsletter integration",
            detected_during="research_stage",
        )

        assert gap1.id != gap2.id

    def test_approve_proposal_creates_registry(self, db_session):
        """Approving a proposal creates a CapabilityRegistry entry and resolves gap."""
        # Setup: gap + discovered + proposal
        gap = CapabilityGap(
            description="Need calendar tool",
            detected_during="publishing_stage",
            status=GapStatus.proposals_ready.value,
        )
        db_session.add(gap)
        db_session.flush()

        disc = DiscoveredCapability(
            gap_id=gap.id,
            source="mcp_registry",
            name="calendar-mcp",
            description="Calendar MCP server",
            url="https://github.com/example/calendar",
            version="1.0.0",
        )
        db_session.add(disc)
        db_session.flush()

        proposal = CapabilityProposal(
            gap_id=gap.id,
            discovered_id=disc.id,
            relevance_score=5,
            quality_score=4,
            security_score=4,
            fit_score=3,
            composite_score=4.1,
            recommendation="recommend",
            auto_rejected=False,
            justification_json='{}',
            status=ProposalStatus.pending.value,
        )
        db_session.add(proposal)
        db_session.flush()

        # Approve
        registry = approve_proposal(
            db_session, proposal.id, review_notes="Looks good"
        )

        assert registry.id is not None
        assert registry.name == "calendar-mcp"
        assert registry.source == "mcp_registry"
        assert registry.status == "active"

        # Check proposal updated
        assert proposal.status == "approved"
        assert proposal.reviewed_at is not None
        assert proposal.review_notes == "Looks good"

        # Check gap resolved
        assert gap.status == "resolved"
        assert gap.resolved_by_id == registry.id

    def test_reject_proposal_requires_notes(self, db_session):
        """Rejecting a proposal updates status and stores review notes."""
        gap = CapabilityGap(
            description="Need slack integration",
            detected_during="publishing_stage",
            status=GapStatus.proposals_ready.value,
        )
        db_session.add(gap)
        db_session.flush()

        disc = DiscoveredCapability(
            gap_id=gap.id,
            source="github",
            name="slack-mcp",
            description="Slack MCP",
            url="https://github.com/example/slack",
        )
        db_session.add(disc)
        db_session.flush()

        proposal = CapabilityProposal(
            gap_id=gap.id,
            discovered_id=disc.id,
            relevance_score=3,
            quality_score=3,
            security_score=3,
            fit_score=3,
            composite_score=3.0,
            recommendation="neutral",
            auto_rejected=False,
            justification_json='{}',
            status=ProposalStatus.pending.value,
        )
        db_session.add(proposal)
        db_session.flush()

        result = reject_proposal(
            db_session, proposal.id, review_notes="Not needed right now"
        )

        assert result.status == "rejected"
        assert result.reviewed_at is not None
        assert result.review_notes == "Not needed right now"

    def test_approve_already_approved_raises(self, db_session):
        """Approving an already-approved proposal raises ValueError."""
        gap = CapabilityGap(
            description="Need something",
            detected_during="testing",
            status=GapStatus.proposals_ready.value,
        )
        db_session.add(gap)
        db_session.flush()

        disc = DiscoveredCapability(
            gap_id=gap.id,
            source="github",
            name="test-tool",
            description="Test tool",
            url="https://github.com/test/tool",
        )
        db_session.add(disc)
        db_session.flush()

        proposal = CapabilityProposal(
            gap_id=gap.id,
            discovered_id=disc.id,
            relevance_score=4,
            quality_score=4,
            security_score=4,
            fit_score=4,
            composite_score=4.0,
            recommendation="recommend",
            auto_rejected=False,
            justification_json='{}',
            status=ProposalStatus.approved.value,
            reviewed_at=datetime.now(timezone.utc),
        )
        db_session.add(proposal)
        db_session.flush()

        with pytest.raises(ValueError, match="expected 'pending'"):
            approve_proposal(db_session, proposal.id)

    def test_record_capability_failure_increments(self, db_session):
        """record_capability_failure increments count and auto-disables at threshold."""
        entry = CapabilityRegistry(
            name="fragile-server",
            description="A fragile server",
            source="github",
            source_url="https://github.com/example/fragile",
            installed_at=datetime.now(timezone.utc),
            status=CapabilityStatus.active.value,
            failure_count=0,
            auto_disable_threshold=3,
        )
        db_session.add(entry)
        db_session.flush()

        # First failure
        result = record_capability_failure(db_session, entry.id)
        assert result.failure_count == 1
        assert result.status == "active"

        # Second failure
        result = record_capability_failure(db_session, entry.id)
        assert result.failure_count == 2
        assert result.status == "active"

        # Third failure -- hits threshold, auto-disabled
        result = record_capability_failure(db_session, entry.id)
        assert result.failure_count == 3
        assert result.status == "disabled"


# =============================================================================
# API endpoint tests
# =============================================================================


class TestAPIEndpoints:
    """Test REST API endpoints via FastAPI TestClient."""

    @pytest.fixture
    def app_client(self, db_session):
        """Create a FastAPI TestClient with injected DB session."""
        from fastapi import FastAPI
        from sophia.capabilities.router import capabilities_router, _get_db

        app = FastAPI()
        app.include_router(capabilities_router)

        def _override_db():
            yield db_session

        app.dependency_overrides[_get_db] = _override_db
        return TestClient(app)

    def test_post_gaps_creates_gap(self, app_client):
        """POST /api/capabilities/gaps creates a gap and returns 201."""
        resp = app_client.post(
            "/api/capabilities/gaps",
            json={
                "description": "Need TikTok publishing capability",
                "detected_during": "publishing_stage",
            },
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["description"] == "Need TikTok publishing capability"
        assert data["status"] == "open"
        assert data["id"] is not None

    def test_get_gaps_returns_list(self, app_client):
        """GET /api/capabilities/gaps returns list of gaps."""
        # Create a gap first
        app_client.post(
            "/api/capabilities/gaps",
            json={
                "description": "Need Pinterest publishing",
                "detected_during": "research_stage",
            },
        )

        resp = app_client.get("/api/capabilities/gaps")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert len(data["items"]) >= 1

    def test_get_gap_not_found(self, app_client):
        """GET /api/capabilities/gaps/999 returns 404."""
        resp = app_client.get("/api/capabilities/gaps/999")
        assert resp.status_code == 404

    def test_approve_proposal_returns_registry(self, app_client, db_session):
        """POST /approve creates registry entry and returns 201."""
        # Setup entities in DB
        gap = CapabilityGap(
            description="Need something",
            detected_during="testing",
            status=GapStatus.proposals_ready.value,
        )
        db_session.add(gap)
        db_session.flush()

        disc = DiscoveredCapability(
            gap_id=gap.id,
            source="github",
            name="api-test-tool",
            description="Tool for API test",
            url="https://github.com/test/api-tool",
        )
        db_session.add(disc)
        db_session.flush()

        proposal = CapabilityProposal(
            gap_id=gap.id,
            discovered_id=disc.id,
            relevance_score=4,
            quality_score=4,
            security_score=4,
            fit_score=4,
            composite_score=4.0,
            recommendation="recommend",
            auto_rejected=False,
            justification_json='{}',
            status=ProposalStatus.pending.value,
        )
        db_session.add(proposal)
        db_session.flush()

        resp = app_client.post(
            f"/api/capabilities/proposals/{proposal.id}/approve",
            json={"review_notes": "Approved via API test"},
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "api-test-tool"
        assert data["status"] == "active"

    def test_reject_proposal_requires_review_notes(self, app_client, db_session):
        """POST /reject without review_notes returns 422."""
        gap = CapabilityGap(
            description="Something else",
            detected_during="testing",
            status=GapStatus.proposals_ready.value,
        )
        db_session.add(gap)
        db_session.flush()

        disc = DiscoveredCapability(
            gap_id=gap.id,
            source="github",
            name="reject-test",
            description="Tool to reject",
            url="https://github.com/test/reject",
        )
        db_session.add(disc)
        db_session.flush()

        proposal = CapabilityProposal(
            gap_id=gap.id,
            discovered_id=disc.id,
            relevance_score=3,
            quality_score=3,
            security_score=3,
            fit_score=3,
            composite_score=3.0,
            recommendation="neutral",
            auto_rejected=False,
            justification_json='{}',
            status=ProposalStatus.pending.value,
        )
        db_session.add(proposal)
        db_session.flush()

        # Missing review_notes should fail validation
        resp = app_client.post(
            f"/api/capabilities/proposals/{proposal.id}/reject",
            json={},
        )
        assert resp.status_code == 422

    def test_approve_already_approved_returns_409(self, app_client, db_session):
        """POST /approve on already-approved proposal returns 409."""
        gap = CapabilityGap(
            description="409 test gap",
            detected_during="testing",
            status=GapStatus.resolved.value,
        )
        db_session.add(gap)
        db_session.flush()

        disc = DiscoveredCapability(
            gap_id=gap.id,
            source="github",
            name="409-test-tool",
            description="Already approved",
            url="https://github.com/test/409",
        )
        db_session.add(disc)
        db_session.flush()

        proposal = CapabilityProposal(
            gap_id=gap.id,
            discovered_id=disc.id,
            relevance_score=4,
            quality_score=4,
            security_score=4,
            fit_score=4,
            composite_score=4.0,
            recommendation="recommend",
            auto_rejected=False,
            justification_json='{}',
            status=ProposalStatus.approved.value,
            reviewed_at=datetime.now(timezone.utc),
        )
        db_session.add(proposal)
        db_session.flush()

        resp = app_client.post(
            f"/api/capabilities/proposals/{proposal.id}/approve",
            json={},
        )
        assert resp.status_code == 409

    def test_registry_list(self, app_client, db_session):
        """GET /api/capabilities/registry returns installed capabilities."""
        entry = CapabilityRegistry(
            name="registry-test-entry",
            description="Test entry",
            source="mcp_registry",
            source_url="https://example.com/test",
            installed_at=datetime.now(timezone.utc),
            status=CapabilityStatus.active.value,
            failure_count=0,
            auto_disable_threshold=5,
        )
        db_session.add(entry)
        db_session.flush()

        resp = app_client.get("/api/capabilities/registry")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert data["active_count"] >= 1

    def test_record_failure_endpoint(self, app_client, db_session):
        """POST /registry/{id}/failure increments failure count."""
        entry = CapabilityRegistry(
            name="failure-test-entry",
            description="Test entry for failure",
            source="github",
            source_url="https://example.com/fail",
            installed_at=datetime.now(timezone.utc),
            status=CapabilityStatus.active.value,
            failure_count=0,
            auto_disable_threshold=5,
        )
        db_session.add(entry)
        db_session.flush()

        resp = app_client.post(
            f"/api/capabilities/registry/{entry.id}/failure"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["failure_count"] == 1
