"""Tests for research engine: sources, service orchestration, schemas, and router.

All MCP server calls are mocked -- tests verify orchestration logic,
circuit breaker behavior, finding creation, scoped queries, digest generation,
and blocklist filtering.
"""

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sophia.intelligence.models import Client
from sophia.intelligence.schemas import ClientCreate, ClientUpdate
from sophia.intelligence.service import ClientService
from sophia.research.models import (
    DECAY_WINDOWS,
    FindingType,
    ResearchFinding,
    relevance_score,
)
from sophia.research.schemas import FindingResponse, ResearchDigest
from sophia.research.service import (
    generate_daily_digest,
    get_findings_for_content,
    run_research_cycle,
)
from sophia.research.sources import CircuitBreaker, MCPSourceRegistry, ResearchScope


# ---------- Circuit Breaker Tests ----------


class TestCircuitBreaker:
    """Test circuit breaker opens after 5 failures and closes after cooldown."""

    def test_starts_closed(self):
        cb = CircuitBreaker("test-source")
        assert cb.is_open() is False
        assert cb.failure_count == 0

    def test_records_success_resets(self):
        cb = CircuitBreaker("test-source")
        cb.failure_count = 3
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.is_open() is False

    def test_opens_after_5_failures(self):
        cb = CircuitBreaker("test-source")
        for _ in range(4):
            cb.record_failure()
            assert cb.is_open() is False

        cb.record_failure()  # 5th failure
        assert cb.is_open() is True
        assert cb.failure_count == 5

    def test_stays_open_before_cooldown(self):
        cb = CircuitBreaker("test-source")
        for _ in range(5):
            cb.record_failure()
        assert cb.is_open() is True

    def test_closes_after_cooldown(self):
        cb = CircuitBreaker("test-source")
        for _ in range(5):
            cb.record_failure()
        assert cb.is_open() is True

        # Simulate cooldown expiry
        cb.last_failure_at = time.time() - CircuitBreaker.COOLDOWN_SECONDS - 1
        assert cb.is_open() is False
        assert cb.failure_count == 0

    def test_records_last_failure_timestamp(self):
        cb = CircuitBreaker("test-source")
        before = time.time()
        cb.record_failure()
        after = time.time()
        assert before <= cb.last_failure_at <= after


# ---------- ResearchScope Tests ----------


class TestResearchScope:
    """Test ResearchScope builds correct queries from client profile."""

    def _make_client(self, **overrides) -> MagicMock:
        """Create a mock client with standard fields."""
        client = MagicMock(spec=Client)
        client.id = 1
        client.geography_area = "Hamilton, Ontario"
        client.geography_radius_km = 50
        client.industry = "Landscaping"
        client.industry_vertical = "landscaping"
        client.market_scope = {
            "location": "Hamilton, Ontario",
            "radius": "50km",
            "source_blocklist": ["spam-site.com"],
        }
        client.content_pillars = ["lawn care tips", "seasonal gardening"]
        for key, val in overrides.items():
            setattr(client, key, val)
        return client

    def test_builds_from_market_scope(self):
        client = self._make_client()
        scope = ResearchScope(client)
        assert scope.location == "Hamilton, Ontario"
        assert scope.radius == "50km"
        assert scope.industry == "landscaping"
        assert scope.blocklist == ["spam-site.com"]

    def test_falls_back_to_direct_fields(self):
        client = self._make_client(market_scope=None)
        scope = ResearchScope(client)
        assert scope.location == "Hamilton, Ontario"
        assert scope.radius == "50km"
        assert scope.industry == "landscaping"
        assert scope.blocklist == []

    def test_scoped_news_query(self):
        client = self._make_client()
        scope = ResearchScope(client)
        query = scope.scoped_news_query("fall cleanup")
        assert query["keyword"] == "fall cleanup Hamilton, Ontario"
        assert query["location"] == "Hamilton, Ontario"
        assert query["limit"] == 5

    def test_scoped_trends_query(self):
        client = self._make_client()
        scope = ResearchScope(client)
        query = scope.scoped_trends_query()
        assert query["geo"] == "CA-ON"
        assert query["limit"] == 10

    def test_scoped_community_query(self):
        client = self._make_client()
        scope = ResearchScope(client)
        query = scope.scoped_community_query("leaf removal")
        assert "leaf removal" in query["keyword"]
        assert "landscaping" in query["keyword"]
        assert "Hamilton, Ontario" in query["keyword"]

    def test_is_blocked_matches_partial(self):
        client = self._make_client()
        scope = ResearchScope(client)
        assert scope.is_blocked("https://spam-site.com/article/123") is True
        assert scope.is_blocked("https://trusted-news.com/article") is False

    def test_is_blocked_empty_blocklist(self):
        client = self._make_client(market_scope={"location": "Hamilton"})
        scope = ResearchScope(client)
        assert scope.is_blocked("https://anything.com") is False

    def test_is_blocked_none_url(self):
        client = self._make_client()
        scope = ResearchScope(client)
        assert scope.is_blocked(None) is False
        assert scope.is_blocked("") is False


# ---------- MCPSourceRegistry Tests ----------


class TestMCPSourceRegistry:
    """Test MCP source registry with circuit breaker integration."""

    @pytest.mark.asyncio
    async def test_query_unknown_source_returns_none(self):
        registry = MCPSourceRegistry()
        result = await registry.query_source("nonexistent", {})
        assert result is None

    @pytest.mark.asyncio
    async def test_query_succeeds_records_success(self):
        registry = MCPSourceRegistry()
        registry.register_source("test-mcp", {"url": "http://test"})

        # Mock the dispatch to return results
        mock_results = [{"title": "Test", "summary": "A test result"}]
        registry._dispatch_query = AsyncMock(return_value=mock_results)

        result = await registry.query_source("test-mcp", {"q": "test"})
        assert result == mock_results
        assert registry._breakers["test-mcp"].failure_count == 0

    @pytest.mark.asyncio
    async def test_query_failure_records_failure(self):
        registry = MCPSourceRegistry()
        registry.register_source("test-mcp", {"url": "http://test"})

        # Mock dispatch to raise
        registry._dispatch_query = AsyncMock(side_effect=ConnectionError("down"))

        result = await registry.query_source("test-mcp", {"q": "test"})
        assert result is None
        assert registry._breakers["test-mcp"].failure_count == 1

    @pytest.mark.asyncio
    async def test_skips_open_circuit_breaker(self):
        registry = MCPSourceRegistry()
        registry.register_source("test-mcp", {"url": "http://test"})

        # Open the breaker
        for _ in range(5):
            registry._breakers["test-mcp"].record_failure()

        result = await registry.query_source("test-mcp", {"q": "test"})
        assert result is None

    @pytest.mark.asyncio
    async def test_filters_blocked_sources(self):
        registry = MCPSourceRegistry()
        registry.register_source("test-mcp", {"url": "http://test"})

        mock_results = [
            {"title": "Good", "summary": "Ok", "url": "https://good-site.com"},
            {"title": "Bad", "summary": "Spam", "url": "https://spam-site.com/post"},
        ]
        registry._dispatch_query = AsyncMock(return_value=mock_results)

        client = MagicMock(spec=Client)
        client.id = 1
        client.market_scope = {"source_blocklist": ["spam-site.com"]}
        client.geography_area = ""
        client.geography_radius_km = None
        client.industry_vertical = ""
        client.industry = ""
        client.content_pillars = []
        scope = ResearchScope(client)

        result = await registry.query_source("test-mcp", {}, scope=scope)
        assert len(result) == 1
        assert result[0]["title"] == "Good"

    def test_get_available_sources(self):
        registry = MCPSourceRegistry()
        registry.register_source("healthy", {})
        registry.register_source("sick", {})
        for _ in range(5):
            registry._breakers["sick"].record_failure()

        available = registry.get_available_sources()
        assert "healthy" in available
        assert "sick" not in available

    def test_get_health_report(self):
        registry = MCPSourceRegistry()
        registry.register_source("good", {})
        registry.register_source("bad", {})
        for _ in range(5):
            registry._breakers["bad"].record_failure()
        registry._breakers["good"].record_failure()  # 1 failure, still closed

        report = registry.get_health_report()
        assert report["good"] == "DEGRADED (failures=1)"
        assert "OPEN" in report["bad"]


# ---------- Research Service Tests ----------


class TestRunResearchCycle:
    """Test the daily research cycle orchestration with mocked MCP sources."""

    @pytest.fixture
    def enriched_client(self, db_session):
        """Create a client with market scope and content pillars."""
        client = ClientService.create_client(
            db_session, ClientCreate(name="Test Landscaper", industry="Landscaping")
        )
        client = ClientService.update_client(
            db_session,
            client.id,
            ClientUpdate(
                industry_vertical="landscaping",
                geography_area="Hamilton, Ontario",
                geography_radius_km=50,
                content_pillars=["lawn care", "seasonal tips"],
                market_scope={
                    "location": "Hamilton, Ontario",
                    "radius": "50km",
                    "source_blocklist": [],
                },
            ),
        )
        return client

    @pytest.mark.asyncio
    async def test_creates_findings_from_mcp_results(self, db_session, enriched_client):
        """Research cycle creates findings with proper fields from MCP results."""
        registry = MCPSourceRegistry()
        registry.register_source("google-news-trends", {})
        registry.register_source("reddit", {})

        # Mock dispatch to return structured results
        news_results = [
            {
                "title": "Hamilton parks upgrade for fall",
                "summary": "City investing in park improvements",
                "source_name": "Hamilton Spectator",
                "url": "https://spec.com/parks",
                "content_angles": ["Share the parks angle"],
            }
        ]
        trends_results = [
            {
                "title": "Outdoor living trending in Ontario",
                "summary": "Google Trends shows outdoor living surge",
                "source_name": "Google Trends",
            }
        ]

        call_count = 0

        async def mock_dispatch(name, params):
            nonlocal call_count
            call_count += 1
            # News queries return news results, trend queries return trends
            if params.get("geo") == "CA-ON":
                return trends_results
            return news_results

        registry._dispatch_query = mock_dispatch

        with patch("sophia.research.service._sync_finding_to_lance", new_callable=AsyncMock):
            with patch("sophia.research.service._feed_intelligence", new_callable=AsyncMock):
                digest = await run_research_cycle(
                    db_session, enriched_client.id, source_registry=registry
                )

        assert isinstance(digest, ResearchDigest)
        assert digest.client_id == enriched_client.id
        assert digest.total_findings > 0

        # Check findings in database
        findings = (
            db_session.query(ResearchFinding)
            .filter(ResearchFinding.client_id == enriched_client.id)
            .all()
        )
        assert len(findings) > 0

        # Verify finding fields
        first = findings[0]
        assert first.topic != ""
        assert first.summary != ""
        assert first.confidence > 0
        assert first.expires_at is not None

    @pytest.mark.asyncio
    async def test_partial_research_continues_on_source_failure(
        self, db_session, enriched_client
    ):
        """Research continues when one source fails (circuit breaker)."""
        registry = MCPSourceRegistry()
        registry.register_source("google-news-trends", {})
        registry.register_source("reddit", {})

        # Open circuit breaker on reddit
        for _ in range(5):
            registry._breakers["reddit"].record_failure()

        # Only news source works
        async def mock_dispatch(name, params):
            if name == "reddit":
                raise ConnectionError("down")
            return [
                {
                    "title": "News item",
                    "summary": "Works fine",
                    "source_name": "CBC News",
                }
            ]

        registry._dispatch_query = mock_dispatch

        with patch("sophia.research.service._sync_finding_to_lance", new_callable=AsyncMock):
            with patch("sophia.research.service._feed_intelligence", new_callable=AsyncMock):
                digest = await run_research_cycle(
                    db_session, enriched_client.id, source_registry=registry
                )

        # Should still have findings from the working source
        assert digest.total_findings > 0


class TestGetFindingsForContent:
    """Test content generation query with relevance filtering."""

    def _create_finding(
        self,
        db,
        client_id,
        finding_type=FindingType.NEWS,
        topic="Test topic",
        summary="Test summary",
        confidence=0.7,
        created_at=None,
        expires_at=None,
        source_url=None,
        is_time_sensitive=0,
    ):
        now = datetime.now(timezone.utc)
        if created_at is None:
            created_at = now
        if expires_at is None:
            expires_at = now + DECAY_WINDOWS[finding_type]

        finding = ResearchFinding(
            client_id=client_id,
            finding_type=finding_type,
            topic=topic,
            summary=summary,
            content_angles=["angle 1"],
            source_url=source_url,
            source_name="test",
            relevance_score_val=1.0,
            confidence=confidence,
            is_time_sensitive=is_time_sensitive,
            expires_at=expires_at,
        )
        db.add(finding)
        db.commit()
        db.refresh(finding)
        return finding

    def test_filters_expired_findings(self, db_session, sample_client):
        """Expired findings are excluded from content queries."""
        # get_findings_for_content imported at module level

        now = datetime.now(timezone.utc)

        # Fresh finding
        self._create_finding(
            db_session,
            sample_client.id,
            topic="Fresh news",
            expires_at=now + timedelta(days=1),
        )

        # Expired finding
        self._create_finding(
            db_session,
            sample_client.id,
            topic="Old news",
            created_at=now - timedelta(days=10),
            expires_at=now - timedelta(days=1),
        )

        results = get_findings_for_content(db_session, sample_client.id)
        assert len(results) == 1
        assert results[0].topic == "Fresh news"

    def test_sorts_by_relevance_times_confidence(self, db_session, sample_client):
        """Results sorted by relevance_score * confidence descending."""
        # get_findings_for_content imported at module level

        now = datetime.now(timezone.utc)

        # High confidence finding
        self._create_finding(
            db_session,
            sample_client.id,
            topic="High confidence",
            confidence=0.9,
            expires_at=now + timedelta(days=2),
        )

        # Low confidence finding
        self._create_finding(
            db_session,
            sample_client.id,
            topic="Low confidence",
            confidence=0.2,
            expires_at=now + timedelta(days=2),
        )

        results = get_findings_for_content(db_session, sample_client.id)
        assert len(results) == 2
        assert results[0].topic == "High confidence"
        assert results[1].topic == "Low confidence"

    def test_excludes_blocked_sources(self, db_session):
        """Findings from blocked sources are filtered out."""
        # get_findings_for_content imported at module level

        # Create client with blocklist
        client = ClientService.create_client(
            db_session, ClientCreate(name="Block Test Client", industry="Tech")
        )
        client = ClientService.update_client(
            db_session,
            client.id,
            ClientUpdate(
                market_scope={"source_blocklist": ["spam.com"]},
            ),
        )

        now = datetime.now(timezone.utc)

        # Clean finding
        self._create_finding(
            db_session,
            client.id,
            topic="Good source",
            source_url="https://news.com/article",
            expires_at=now + timedelta(days=2),
        )

        # Blocked finding
        self._create_finding(
            db_session,
            client.id,
            topic="Blocked source",
            source_url="https://spam.com/clickbait",
            expires_at=now + timedelta(days=2),
        )

        results = get_findings_for_content(db_session, client.id)
        assert len(results) == 1
        assert results[0].topic == "Good source"


class TestGenerateDailyDigest:
    """Test daily digest generation with freshness and source health."""

    def test_groups_by_type(self, db_session, sample_client):
        """Digest groups findings by finding type."""
        # generate_daily_digest imported at module level

        now = datetime.now(timezone.utc)

        # Create findings of different types
        for ftype, topic in [
            (FindingType.NEWS, "News item"),
            (FindingType.TREND, "Trending topic"),
            (FindingType.COMMUNITY, "Community post"),
        ]:
            finding = ResearchFinding(
                client_id=sample_client.id,
                finding_type=ftype,
                topic=topic,
                summary=f"Summary for {topic}",
                relevance_score_val=1.0,
                confidence=0.7,
                is_time_sensitive=0,
                expires_at=now + DECAY_WINDOWS[ftype],
            )
            db_session.add(finding)
        db_session.commit()

        digest = generate_daily_digest(db_session, sample_client.id)

        assert isinstance(digest, ResearchDigest)
        assert "news" in digest.findings_by_type
        assert "trend" in digest.findings_by_type
        assert "community" in digest.findings_by_type
        assert digest.total_findings == 3

    def test_includes_freshness_metric(self, db_session, sample_client):
        """Digest includes research freshness percentage."""
        # generate_daily_digest imported at module level

        now = datetime.now(timezone.utc)

        # Create one fresh and one expired finding
        fresh = ResearchFinding(
            client_id=sample_client.id,
            finding_type=FindingType.NEWS,
            topic="Fresh",
            summary="Recent news",
            relevance_score_val=1.0,
            confidence=0.7,
            is_time_sensitive=0,
            expires_at=now + timedelta(days=2),
        )
        expired = ResearchFinding(
            client_id=sample_client.id,
            finding_type=FindingType.NEWS,
            topic="Expired",
            summary="Old news",
            relevance_score_val=0.0,
            confidence=0.5,
            is_time_sensitive=0,
            expires_at=now - timedelta(days=1),
        )
        db_session.add(fresh)
        db_session.add(expired)
        db_session.commit()

        digest = generate_daily_digest(db_session, sample_client.id)

        # Freshness should be 50% (1 of 2 within decay window)
        assert digest.research_freshness_pct == 50.0

    def test_includes_source_health(self, db_session, sample_client):
        """Digest includes MCP source health report."""
        # generate_daily_digest imported at module level

        registry = MCPSourceRegistry()
        registry.register_source("google-news-trends", {})
        registry.register_source("reddit", {})
        # Open reddit breaker
        for _ in range(5):
            registry._breakers["reddit"].record_failure()

        digest = generate_daily_digest(
            db_session, sample_client.id, source_registry=registry
        )

        assert "google-news-trends" in digest.source_health
        assert "reddit" in digest.source_health
        assert "OPEN" in digest.source_health["reddit"]

    def test_time_sensitive_alerts_at_top(self, db_session, sample_client):
        """Time-sensitive findings are surfaced in alerts list."""
        # generate_daily_digest imported at module level

        now = datetime.now(timezone.utc)

        normal = ResearchFinding(
            client_id=sample_client.id,
            finding_type=FindingType.NEWS,
            topic="Normal news",
            summary="Regular",
            relevance_score_val=1.0,
            confidence=0.7,
            is_time_sensitive=0,
            expires_at=now + timedelta(days=2),
        )
        urgent = ResearchFinding(
            client_id=sample_client.id,
            finding_type=FindingType.NEWS,
            topic="Urgent event",
            summary="Happening soon",
            relevance_score_val=1.0,
            confidence=0.8,
            is_time_sensitive=1,
            expires_at=now + timedelta(days=1),
        )
        db_session.add(normal)
        db_session.add(urgent)
        db_session.commit()

        digest = generate_daily_digest(db_session, sample_client.id)

        assert len(digest.time_sensitive_alerts) == 1
        assert digest.time_sensitive_alerts[0].topic == "Urgent event"

    def test_empty_digest(self, db_session, sample_client):
        """Digest with no findings returns valid empty structure."""
        # generate_daily_digest imported at module level

        digest = generate_daily_digest(db_session, sample_client.id)
        assert digest.total_findings == 0
        assert digest.research_freshness_pct == 0.0
        assert digest.findings_by_type == {}
