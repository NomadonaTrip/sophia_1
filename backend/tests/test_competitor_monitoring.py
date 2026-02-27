"""Tests for competitor monitoring: snapshots, opportunity detection, benchmarking.

All MCP server calls are mocked -- tests verify monitoring logic,
opportunity classification, inactivity detection, and benchmarking.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from sophia.intelligence.models import Client
from sophia.intelligence.schemas import ClientCreate, ClientUpdate
from sophia.intelligence.service import ClientService
from sophia.research.competitor import (
    compute_competitive_benchmarks,
    detect_competitor_inactivity,
    detect_opportunities,
    monitor_competitors,
    propose_new_competitors,
)
from sophia.research.models import Competitor, CompetitorSnapshot
from sophia.research.sources import MCPSourceRegistry


@pytest.fixture
def landscaping_client(db_session):
    """Create a landscaping client with content pillars and competitors."""
    client = ClientService.create_client(
        db_session, ClientCreate(name="Green Thumb Pro", industry="Landscaping")
    )
    client = ClientService.update_client(
        db_session,
        client.id,
        ClientUpdate(
            industry_vertical="landscaping",
            geography_area="Hamilton, Ontario",
            geography_radius_km=50,
            content_pillars=["lawn care", "seasonal tips", "hardscaping"],
            market_scope={
                "location": "Hamilton, Ontario",
                "radius": "50km",
                "source_blocklist": [],
            },
        ),
    )
    return client


@pytest.fixture
def primary_competitor(db_session, landscaping_client):
    """Create a primary competitor for the landscaping client."""
    comp = Competitor(
        client_id=landscaping_client.id,
        name="Rival Landscaping Co",
        platform_urls={"facebook": "https://facebook.com/rival", "instagram": "https://instagram.com/rival"},
        is_primary=1,
        is_operator_approved=1,
        discovered_by="operator",
        monitoring_frequency="daily",
    )
    db_session.add(comp)
    db_session.commit()
    db_session.refresh(comp)
    return comp


@pytest.fixture
def watchlist_competitor(db_session, landscaping_client):
    """Create a watchlist competitor with recent monitoring."""
    now = datetime.now(timezone.utc)
    comp = Competitor(
        client_id=landscaping_client.id,
        name="Watchlist Gardens",
        platform_urls={"facebook": "https://facebook.com/watchlist"},
        is_primary=0,
        is_operator_approved=1,
        discovered_by="sophia",
        monitoring_frequency="monthly",
        last_monitored_at=now - timedelta(days=10),  # Recently checked
    )
    db_session.add(comp)
    db_session.commit()
    db_session.refresh(comp)
    return comp


@pytest.fixture
def stale_watchlist_competitor(db_session, landscaping_client):
    """Create a watchlist competitor that hasn't been checked in 45 days."""
    now = datetime.now(timezone.utc)
    comp = Competitor(
        client_id=landscaping_client.id,
        name="Stale Gardens",
        platform_urls={"facebook": "https://facebook.com/stale"},
        is_primary=0,
        is_operator_approved=1,
        discovered_by="sophia",
        monitoring_frequency="monthly",
        last_monitored_at=now - timedelta(days=45),  # Stale
    )
    db_session.add(comp)
    db_session.commit()
    db_session.refresh(comp)
    return comp


def _make_mocked_registry(social_data: dict | None = None) -> MCPSourceRegistry:
    """Create an MCPSourceRegistry with mocked MCP dispatch."""
    registry = MCPSourceRegistry()
    registry.register_source("brightdata", {"url": "http://bright"})
    registry.register_source("firecrawl", {"url": "http://firecrawl"})

    if social_data is None:
        social_data = {
            "post_frequency_7d": 5,
            "avg_engagement_rate": 3.2,
            "top_content_themes": ["lawn care", "garden design"],
            "content_tone": "professional",
            "detected_gaps": [],
            "detected_threats": [],
        }

    async def mock_dispatch(name, params):
        return [social_data]

    registry._dispatch_query = mock_dispatch
    return registry


# ---------- monitor_competitors Tests ----------


class TestMonitorCompetitors:
    """Test competitor monitoring creates snapshots correctly."""

    @pytest.mark.asyncio
    async def test_creates_snapshots_for_primary(
        self, db_session, landscaping_client, primary_competitor
    ):
        """Primary competitors get monitored and snapshot created."""
        registry = _make_mocked_registry()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "sophia.research.competitor._sync_snapshot_to_lance",
                AsyncMock(),
            )
            snapshots = await monitor_competitors(
                db_session, landscaping_client.id, registry
            )

        assert len(snapshots) == 1
        snap = snapshots[0]
        assert snap.client_id == landscaping_client.id
        assert snap.competitor_id == primary_competitor.id
        assert snap.post_frequency_7d == 5
        assert snap.avg_engagement_rate == 3.2
        assert snap.top_content_themes == ["lawn care", "garden design"]
        assert snap.content_tone == "professional"

    @pytest.mark.asyncio
    async def test_skips_recently_monitored_watchlist(
        self, db_session, landscaping_client, watchlist_competitor
    ):
        """Watchlist competitors checked within 30 days are skipped."""
        registry = _make_mocked_registry()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "sophia.research.competitor._sync_snapshot_to_lance",
                AsyncMock(),
            )
            snapshots = await monitor_competitors(
                db_session, landscaping_client.id, registry
            )

        # Watchlist competitor was checked 10 days ago, should be skipped
        assert len(snapshots) == 0

    @pytest.mark.asyncio
    async def test_monitors_stale_watchlist(
        self, db_session, landscaping_client, stale_watchlist_competitor
    ):
        """Watchlist competitors not checked for >30 days get monitored."""
        registry = _make_mocked_registry()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "sophia.research.competitor._sync_snapshot_to_lance",
                AsyncMock(),
            )
            snapshots = await monitor_competitors(
                db_session, landscaping_client.id, registry
            )

        assert len(snapshots) == 1
        assert snapshots[0].competitor_id == stale_watchlist_competitor.id

    @pytest.mark.asyncio
    async def test_updates_last_monitored_at(
        self, db_session, landscaping_client, primary_competitor
    ):
        """Monitoring updates the competitor's last_monitored_at timestamp."""
        registry = _make_mocked_registry()
        before = primary_competitor.last_monitored_at

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "sophia.research.competitor._sync_snapshot_to_lance",
                AsyncMock(),
            )
            await monitor_competitors(
                db_session, landscaping_client.id, registry
            )

        db_session.refresh(primary_competitor)
        assert primary_competitor.last_monitored_at is not None
        assert primary_competitor.last_monitored_at != before


# ---------- detect_opportunities Tests ----------


class TestDetectOpportunities:
    """Test opportunity detection classifies correctly."""

    def _add_snapshot(
        self,
        db,
        client_id,
        competitor_id,
        themes=None,
        gaps=None,
        threats=None,
        engagement=2.0,
        opp_type=None,
    ):
        snap = CompetitorSnapshot(
            client_id=client_id,
            competitor_id=competitor_id,
            post_frequency_7d=5,
            avg_engagement_rate=engagement,
            top_content_themes=themes or [],
            content_tone="professional",
            detected_gaps=gaps,
            detected_threats=threats,
            opportunity_type=opp_type,
        )
        db.add(snap)
        db.commit()
        db.refresh(snap)
        return snap

    def test_detects_content_gaps_proactive(
        self, db_session, landscaping_client, primary_competitor
    ):
        """Content gaps where client has pillars competitors don't are proactive."""
        # Competitor covers lawn care and garden design, but NOT hardscaping or seasonal tips
        self._add_snapshot(
            db_session,
            landscaping_client.id,
            primary_competitor.id,
            themes=["lawn care", "garden design"],
        )

        opps = detect_opportunities(db_session, landscaping_client.id)

        # Client has "seasonal tips" and "hardscaping" not covered by competitors
        gap_opps = [o for o in opps if o["type"] == "content_gap" and o.get("classification") == "proactive"]
        gap_topics = [o.get("topic", "") for o in gap_opps]
        assert "seasonal tips" in gap_topics or "hardscaping" in gap_topics

    def test_detects_winning_formats_reactive(
        self, db_session, landscaping_client, primary_competitor
    ):
        """High-engagement themes from competitors are reactive opportunities."""
        # Competitor gets high engagement on "drone footage" (not in client pillars)
        self._add_snapshot(
            db_session,
            landscaping_client.id,
            primary_competitor.id,
            themes=["drone footage", "lawn care"],
            engagement=5.0,
        )

        opps = detect_opportunities(db_session, landscaping_client.id)

        winning = [o for o in opps if o["type"] == "winning_format"]
        assert any("drone footage" in o["description"] for o in winning)
        assert all(o["classification"] == "reactive" for o in winning)

    def test_surfaces_explicit_gaps_and_threats(
        self, db_session, landscaping_client, primary_competitor
    ):
        """Explicit gaps and threats from snapshots are surfaced."""
        self._add_snapshot(
            db_session,
            landscaping_client.id,
            primary_competitor.id,
            gaps=["No competitor covers winter maintenance"],
            threats=["Rival launched TikTok presence with 10k followers"],
        )

        opps = detect_opportunities(db_session, landscaping_client.id)

        gap_opps = [o for o in opps if o["type"] == "content_gap"]
        assert any("winter maintenance" in o["description"] for o in gap_opps)

        threat_opps = [o for o in opps if o["type"] == "competitive_threat"]
        assert any("TikTok" in o["description"] for o in threat_opps)

    def test_classifies_reactive_vs_proactive(
        self, db_session, landscaping_client, primary_competitor
    ):
        """Opportunities are correctly classified."""
        self._add_snapshot(
            db_session,
            landscaping_client.id,
            primary_competitor.id,
            themes=["video tours"],
            engagement=4.5,
            gaps=["Nobody covers composting"],
            threats=["Competitor went viral"],
        )

        opps = detect_opportunities(db_session, landscaping_client.id)

        for opp in opps:
            assert opp["classification"] in ("reactive", "proactive")


# ---------- propose_new_competitors Tests ----------


class TestProposeNewCompetitors:
    """Test new competitor proposal with deduplication."""

    @pytest.mark.asyncio
    async def test_deduplicates_against_existing(
        self, db_session, landscaping_client, primary_competitor
    ):
        """Proposals exclude competitors already being tracked."""
        registry = MCPSourceRegistry()
        registry.register_source("brightdata", {})

        async def mock_dispatch(name, params):
            return [
                {
                    "name": "Rival Landscaping Co",  # Already tracked
                    "platform_urls": {"facebook": "https://fb.com/rival"},
                },
                {
                    "name": "New Gardens LLC",  # New
                    "platform_urls": {"facebook": "https://fb.com/newgardens"},
                },
            ]

        registry._dispatch_query = mock_dispatch

        proposals = await propose_new_competitors(
            db_session, landscaping_client.id, registry
        )

        names = [p["name"] for p in proposals]
        assert "Rival Landscaping Co" not in names
        assert "New Gardens LLC" in names

    @pytest.mark.asyncio
    async def test_includes_context_and_recommendation(
        self, db_session, landscaping_client
    ):
        """Proposals include reason and recommended monitoring level."""
        registry = MCPSourceRegistry()
        registry.register_source("brightdata", {})

        async def mock_dispatch(name, params):
            return [
                {
                    "name": "Active Competitor",
                    "platform_urls": {"facebook": "https://fb.com/active"},
                    "post_frequency_7d": 7,
                    "avg_engagement_rate": 4.0,
                },
                {
                    "name": "Quiet Competitor",
                    "platform_urls": {},
                    "post_frequency_7d": 1,
                    "avg_engagement_rate": 0.5,
                },
            ]

        registry._dispatch_query = mock_dispatch

        proposals = await propose_new_competitors(
            db_session, landscaping_client.id, registry
        )

        assert len(proposals) == 2
        active = next(p for p in proposals if p["name"] == "Active Competitor")
        quiet = next(p for p in proposals if p["name"] == "Quiet Competitor")

        assert active["recommended_level"] == "primary"
        assert quiet["recommended_level"] == "watchlist"
        assert "message" in active


# ---------- detect_competitor_inactivity Tests ----------


class TestDetectCompetitorInactivity:
    """Test inactivity detection flags quiet competitors."""

    def test_flags_50_pct_drop(
        self, db_session, landscaping_client, primary_competitor
    ):
        """Competitor with >50% frequency drop over 2+ snapshots is flagged."""
        now = datetime.now(timezone.utc)

        # Historical snapshots with normal frequency
        for i in range(4, 0, -1):
            snap = CompetitorSnapshot(
                client_id=landscaping_client.id,
                competitor_id=primary_competitor.id,
                post_frequency_7d=10,
                avg_engagement_rate=3.0,
            )
            db_session.add(snap)
        db_session.commit()

        # Two recent snapshots with dramatic drop
        for _ in range(2):
            snap = CompetitorSnapshot(
                client_id=landscaping_client.id,
                competitor_id=primary_competitor.id,
                post_frequency_7d=2,
                avg_engagement_rate=1.0,
            )
            db_session.add(snap)
        db_session.commit()

        alerts = detect_competitor_inactivity(db_session, landscaping_client.id)

        assert len(alerts) == 1
        assert alerts[0]["competitor_name"] == "Rival Landscaping Co"
        assert alerts[0]["drop_percentage"] >= 50.0

    def test_no_flag_for_normal_activity(
        self, db_session, landscaping_client, primary_competitor
    ):
        """No alert for competitors maintaining normal posting frequency."""
        # Consistent activity
        for _ in range(5):
            snap = CompetitorSnapshot(
                client_id=landscaping_client.id,
                competitor_id=primary_competitor.id,
                post_frequency_7d=8,
                avg_engagement_rate=3.0,
            )
            db_session.add(snap)
        db_session.commit()

        alerts = detect_competitor_inactivity(db_session, landscaping_client.id)
        assert len(alerts) == 0

    def test_needs_multiple_snapshots(
        self, db_session, landscaping_client, primary_competitor
    ):
        """No flag with only 1 snapshot (insufficient history)."""
        snap = CompetitorSnapshot(
            client_id=landscaping_client.id,
            competitor_id=primary_competitor.id,
            post_frequency_7d=1,
            avg_engagement_rate=0.5,
        )
        db_session.add(snap)
        db_session.commit()

        alerts = detect_competitor_inactivity(db_session, landscaping_client.id)
        assert len(alerts) == 0


# ---------- compute_competitive_benchmarks Tests ----------


class TestComputeCompetitiveBenchmarks:
    """Test competitive benchmarking returns relative metrics."""

    def test_returns_averages_from_snapshots(
        self, db_session, landscaping_client
    ):
        """Benchmarks compute averages from latest snapshot per competitor."""
        # Create two primary competitors with snapshots
        comp1 = Competitor(
            client_id=landscaping_client.id,
            name="Comp A",
            is_primary=1,
        )
        comp2 = Competitor(
            client_id=landscaping_client.id,
            name="Comp B",
            is_primary=1,
        )
        db_session.add(comp1)
        db_session.add(comp2)
        db_session.commit()
        db_session.refresh(comp1)
        db_session.refresh(comp2)

        # Snapshots
        snap1 = CompetitorSnapshot(
            client_id=landscaping_client.id,
            competitor_id=comp1.id,
            post_frequency_7d=6,
            avg_engagement_rate=3.0,
        )
        snap2 = CompetitorSnapshot(
            client_id=landscaping_client.id,
            competitor_id=comp2.id,
            post_frequency_7d=10,
            avg_engagement_rate=5.0,
        )
        db_session.add(snap1)
        db_session.add(snap2)
        db_session.commit()

        benchmarks = compute_competitive_benchmarks(
            db_session, landscaping_client.id
        )

        assert benchmarks["competitor_count"] == 2
        assert benchmarks["post_frequency"]["competitor_avg"] == 8.0
        assert benchmarks["engagement_rate"]["competitor_avg"] == 4.0
        assert benchmarks["post_frequency"]["status"] == "data_available"

    def test_no_competitors_returns_no_data(self, db_session, landscaping_client):
        """Benchmarks with no competitors return no_data status."""
        benchmarks = compute_competitive_benchmarks(
            db_session, landscaping_client.id
        )

        assert benchmarks["competitor_count"] == 0
        assert benchmarks["post_frequency"]["status"] == "no_data"

    def test_only_primary_competitors_used(
        self, db_session, landscaping_client, primary_competitor, watchlist_competitor
    ):
        """Only primary competitors (not watchlist) are used for benchmarks."""
        snap = CompetitorSnapshot(
            client_id=landscaping_client.id,
            competitor_id=primary_competitor.id,
            post_frequency_7d=8,
            avg_engagement_rate=4.0,
        )
        db_session.add(snap)
        db_session.commit()

        benchmarks = compute_competitive_benchmarks(
            db_session, landscaping_client.id
        )

        # Only 1 primary competitor counted
        assert benchmarks["competitor_count"] == 1
        assert benchmarks["post_frequency"]["competitor_avg"] == 8.0
