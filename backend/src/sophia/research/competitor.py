"""Competitor monitoring: snapshot collection, opportunity detection, gap analysis.

Tracks competitor social media activity via MCP sources, creates point-in-time
snapshots with engagement metrics and content themes, detects content gaps and
competitive threats, proposes new competitors, and computes relative benchmarks.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from sophia.research.models import Competitor, CompetitorSnapshot
from sophia.research.sources import MCPSourceRegistry, ResearchScope

logger = logging.getLogger(__name__)


async def monitor_competitors(
    db: Session,
    client_id: int,
    source_registry: MCPSourceRegistry,
) -> list[CompetitorSnapshot]:
    """Monitor competitors for a given client.

    Primary competitors (is_primary=1) are checked daily.
    Watchlist competitors are checked only if last_monitored_at > 30 days ago.

    For each competitor to check:
    1. Query social media MCP sources for public page data
    2. Create CompetitorSnapshot with metrics
    3. Update competitor.last_monitored_at
    4. Write-through sync to LanceDB

    Args:
        db: SQLAlchemy session.
        client_id: Client ID.
        source_registry: MCP source registry for social media queries.

    Returns:
        List of newly created CompetitorSnapshot records.
    """
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)

    competitors = (
        db.query(Competitor)
        .filter(Competitor.client_id == client_id)
        .all()
    )

    snapshots: list[CompetitorSnapshot] = []

    for competitor in competitors:
        # Primary: check every cycle. Watchlist: only if stale (>30 days)
        if not competitor.is_primary:
            last_check = competitor.last_monitored_at
            if last_check is not None:
                if last_check.tzinfo is None:
                    last_check = last_check.replace(tzinfo=timezone.utc)
                if last_check > thirty_days_ago:
                    continue  # Watchlist competitor recently checked

        # Query social media MCP for competitor data
        raw_data = await _fetch_competitor_data(
            competitor, source_registry
        )

        # Create snapshot from raw data
        snapshot = _create_snapshot(
            db, client_id, competitor.id, raw_data, now
        )
        snapshots.append(snapshot)

        # Update monitoring timestamp
        competitor.last_monitored_at = now

    if snapshots:
        db.commit()

        # Write-through sync to LanceDB
        for snapshot in snapshots:
            db.refresh(snapshot)
            await _sync_snapshot_to_lance(snapshot)

    return snapshots


async def _fetch_competitor_data(
    competitor: Competitor,
    source_registry: MCPSourceRegistry,
) -> dict:
    """Fetch competitor social media data via MCP sources.

    Queries Bright Data Social Media MCP (or fallback sources) for
    public page data: post count, engagement rates, content themes, tone.

    Args:
        competitor: Competitor model instance.
        source_registry: MCP source registry.

    Returns:
        Raw data dict with social media metrics.
    """
    # Build query from competitor's platform URLs
    platform_urls = competitor.platform_urls or {}
    params = {
        "name": competitor.name,
        "platform_urls": platform_urls,
        "metrics": ["post_frequency", "engagement_rate", "content_themes", "tone"],
    }

    # Try Bright Data Social Media MCP first
    result = await source_registry.query_source("brightdata", params)
    if result and len(result) > 0:
        return result[0]

    # Fallback to firecrawl for web scraping
    result = await source_registry.query_source("firecrawl", params)
    if result and len(result) > 0:
        return result[0]

    # Return empty data if no sources available
    return {}


def _create_snapshot(
    db: Session,
    client_id: int,
    competitor_id: int,
    raw_data: dict,
    now: datetime,
) -> CompetitorSnapshot:
    """Create a CompetitorSnapshot from raw MCP data.

    Extracts post frequency, engagement, content themes, tone,
    and detects gaps and threats from the data.
    """
    # Extract metrics from raw data
    post_frequency = raw_data.get("post_frequency_7d")
    engagement_rate = raw_data.get("avg_engagement_rate")
    themes = raw_data.get("top_content_themes", [])
    tone = raw_data.get("content_tone")

    # Detect gaps and threats from data
    gaps = raw_data.get("detected_gaps", [])
    threats = raw_data.get("detected_threats", [])
    opp_type = raw_data.get("opportunity_type")

    snapshot = CompetitorSnapshot(
        client_id=client_id,
        competitor_id=competitor_id,
        post_frequency_7d=post_frequency,
        avg_engagement_rate=engagement_rate,
        top_content_themes=themes if themes else None,
        content_tone=tone,
        detected_gaps=gaps if gaps else None,
        detected_threats=threats if threats else None,
        opportunity_type=opp_type,
    )
    db.add(snapshot)
    return snapshot


async def _sync_snapshot_to_lance(snapshot: CompetitorSnapshot) -> None:
    """Write-through sync a competitor snapshot to LanceDB."""
    try:
        from sophia.semantic.sync import sync_to_lance

        themes_text = ", ".join(snapshot.top_content_themes or [])
        text = f"Competitor snapshot: {themes_text}"

        await sync_to_lance(
            record_type="competitor_snapshots",
            record_id=snapshot.id,
            text=text,
            metadata={
                "client_id": snapshot.client_id,
                "domain": "competitor",
                "created_at": (
                    snapshot.created_at.isoformat()
                    if snapshot.created_at
                    else datetime.now(timezone.utc).isoformat()
                ),
            },
        )
    except Exception:
        logger.exception(
            "Write-through sync failed for competitor snapshot %d",
            snapshot.id,
        )


def detect_opportunities(
    db: Session,
    client_id: int,
) -> list[dict]:
    """Analyze recent competitor snapshots to find strategic opportunities.

    Finds:
    - Content gaps: topics competitors aren't covering that align with client pillars
    - Winning formats: high-engagement content types client hasn't tried
    - Competitive threats: competitor content outperforming client in same topics
    - Each classified as "reactive" (respond to competitor move) or "proactive" (own the gap)

    Args:
        db: SQLAlchemy session.
        client_id: Client ID.

    Returns:
        List of opportunity dicts with type, description, classification.
    """
    from sophia.intelligence.models import Client

    # Load client for content pillar context
    client = db.query(Client).filter(Client.id == client_id).first()
    client_pillars = set(p.lower() for p in (client.content_pillars or []))

    # Get recent snapshots (last 30 days)
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    snapshots = (
        db.query(CompetitorSnapshot)
        .filter(
            CompetitorSnapshot.client_id == client_id,
        )
        .all()
    )

    # Filter to recent snapshots
    recent_snapshots = []
    for s in snapshots:
        created = s.created_at
        if created is not None:
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created >= thirty_days_ago:
                recent_snapshots.append(s)
        else:
            recent_snapshots.append(s)  # Include if no timestamp

    opportunities: list[dict] = []

    # Aggregate competitor themes and gaps
    all_competitor_themes: set[str] = set()
    all_gaps: list[str] = []
    all_threats: list[str] = []
    high_engagement_themes: list[tuple[str, float]] = []

    for snapshot in recent_snapshots:
        themes = snapshot.top_content_themes or []
        for theme in themes:
            all_competitor_themes.add(theme.lower())

        if snapshot.detected_gaps:
            all_gaps.extend(snapshot.detected_gaps)

        if snapshot.detected_threats:
            all_threats.extend(snapshot.detected_threats)

        # Track high-engagement themes
        if snapshot.avg_engagement_rate and snapshot.avg_engagement_rate > 3.0:
            for theme in themes:
                high_engagement_themes.append((theme, snapshot.avg_engagement_rate))

    # Content gaps: client pillars not covered by competitors
    if client_pillars:
        uncovered = client_pillars - all_competitor_themes
        for topic in uncovered:
            opportunities.append({
                "type": "content_gap",
                "description": f"No competitors covering '{topic}' -- opportunity to own this topic",
                "classification": "proactive",
                "topic": topic,
            })

    # Winning formats: high-engagement themes client could try
    for theme, engagement in high_engagement_themes:
        if theme.lower() not in client_pillars:
            opportunities.append({
                "type": "winning_format",
                "description": (
                    f"Competitor getting {engagement:.1f}% engagement "
                    f"on '{theme}' content -- consider adding to your mix"
                ),
                "classification": "reactive",
                "topic": theme,
            })

    # Explicit gaps from snapshots
    for gap in all_gaps:
        opportunities.append({
            "type": "content_gap",
            "description": gap,
            "classification": "proactive",
        })

    # Competitive threats
    for threat in all_threats:
        opportunities.append({
            "type": "competitive_threat",
            "description": threat,
            "classification": "reactive",
        })

    return opportunities


async def propose_new_competitors(
    db: Session,
    client_id: int,
    source_registry: MCPSourceRegistry,
) -> list[dict]:
    """Research and propose new competitors to monitor.

    1. Use client's market scope to search for businesses in same industry + location
    2. Cross-reference against existing competitor list
    3. Return proposals with context and recommended monitoring level

    Args:
        db: SQLAlchemy session.
        client_id: Client ID.
        source_registry: MCP source registry.

    Returns:
        List of proposal dicts with name, urls, reason, recommended_level.
    """
    from sophia.intelligence.models import Client

    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        return []

    scope = ResearchScope(client)

    # Search for businesses in same industry + location
    params = {
        "industry": scope.industry,
        "location": scope.location,
        "limit": 10,
    }

    results = await source_registry.query_source(
        "brightdata", params, scope=scope
    )
    if not results:
        results = await source_registry.query_source(
            "firecrawl", params, scope=scope
        )

    if not results:
        return []

    # Get existing competitor names for dedup
    existing = (
        db.query(Competitor.name)
        .filter(Competitor.client_id == client_id)
        .all()
    )
    existing_names = {n.lower() for (n,) in existing}

    proposals: list[dict] = []
    for result in results:
        name = result.get("name", result.get("business_name", ""))
        if not name or name.lower() in existing_names:
            continue

        # Don't propose the client themselves
        if name.lower() == client.name.lower():
            continue

        platform_urls = result.get("platform_urls", {})
        reason = result.get("relevance_reason", f"Same industry ({scope.industry}) in {scope.location}")

        proposals.append({
            "name": name,
            "platform_urls": platform_urls,
            "reason": reason,
            "recommended_level": _recommend_monitoring_level(result),
            "message": (
                f"Found a potential competitor: {name}. "
                f"They operate in {scope.industry} in {scope.location}. "
                f"Want me to track them?"
            ),
        })

    return proposals


def _recommend_monitoring_level(raw_data: dict) -> str:
    """Recommend monitoring level based on competitor data richness.

    Primary if they have strong social presence, watchlist otherwise.
    """
    post_freq = raw_data.get("post_frequency_7d", 0)
    engagement = raw_data.get("avg_engagement_rate", 0)

    if post_freq and post_freq >= 3 and engagement and engagement >= 2.0:
        return "primary"
    return "watchlist"


def detect_competitor_inactivity(
    db: Session,
    client_id: int,
) -> list[dict]:
    """Flag competitors that have gone unusually quiet.

    Compares current post_frequency_7d against historical average.
    Flags if >50% drop sustained for 2+ weeks of snapshots.

    Args:
        db: SQLAlchemy session.
        client_id: Client ID.

    Returns:
        List of inactivity alert dicts.
    """
    competitors = (
        db.query(Competitor)
        .filter(Competitor.client_id == client_id)
        .all()
    )

    alerts: list[dict] = []

    for competitor in competitors:
        snapshots = (
            db.query(CompetitorSnapshot)
            .filter(CompetitorSnapshot.competitor_id == competitor.id)
            .order_by(CompetitorSnapshot.id.desc())
            .limit(10)
            .all()
        )

        if len(snapshots) < 2:
            continue

        # Compute historical average (excluding most recent)
        historical = [
            s.post_frequency_7d
            for s in snapshots[1:]
            if s.post_frequency_7d is not None
        ]
        if not historical:
            continue

        avg_historical = sum(historical) / len(historical)
        if avg_historical == 0:
            continue

        # Check most recent snapshot
        latest = snapshots[0]
        if latest.post_frequency_7d is None:
            continue

        drop_pct = 1 - (latest.post_frequency_7d / avg_historical)

        if drop_pct >= 0.5:
            # Check if sustained: look at 2 most recent
            recent_two = [
                s.post_frequency_7d
                for s in snapshots[:2]
                if s.post_frequency_7d is not None
            ]
            if len(recent_two) >= 2 and all(
                freq < avg_historical * 0.5 for freq in recent_two
            ):
                alerts.append({
                    "competitor_id": competitor.id,
                    "competitor_name": competitor.name,
                    "current_frequency": latest.post_frequency_7d,
                    "historical_average": round(avg_historical, 1),
                    "drop_percentage": round(drop_pct * 100, 1),
                    "message": (
                        f"{competitor.name} has gone quiet: "
                        f"posting {latest.post_frequency_7d}/week vs "
                        f"usual {avg_historical:.0f}/week "
                        f"({drop_pct * 100:.0f}% drop)"
                    ),
                })

    return alerts


def compute_competitive_benchmarks(
    db: Session,
    client_id: int,
) -> dict:
    """Compute relative performance benchmarks vs competitors.

    Compares:
    - Post frequency: client vs competitor average
    - Engagement rate: client vs competitor average
    - Provides context for over/under performance

    Args:
        db: SQLAlchemy session.
        client_id: Client ID.

    Returns:
        Benchmark report dict.
    """
    # Get most recent snapshot per competitor
    competitors = (
        db.query(Competitor)
        .filter(
            Competitor.client_id == client_id,
            Competitor.is_primary == 1,
        )
        .all()
    )

    if not competitors:
        return {
            "client_id": client_id,
            "competitor_count": 0,
            "post_frequency": {"client": None, "competitor_avg": None, "status": "no_data"},
            "engagement_rate": {"client": None, "competitor_avg": None, "status": "no_data"},
        }

    # Collect most recent snapshot per competitor
    frequencies: list[int] = []
    engagement_rates: list[float] = []

    for comp in competitors:
        latest = (
            db.query(CompetitorSnapshot)
            .filter(CompetitorSnapshot.competitor_id == comp.id)
            .order_by(CompetitorSnapshot.created_at.desc())
            .first()
        )
        if latest:
            if latest.post_frequency_7d is not None:
                frequencies.append(latest.post_frequency_7d)
            if latest.avg_engagement_rate is not None:
                engagement_rates.append(latest.avg_engagement_rate)

    # Compute averages
    avg_freq = sum(frequencies) / len(frequencies) if frequencies else None
    avg_eng = sum(engagement_rates) / len(engagement_rates) if engagement_rates else None

    return {
        "client_id": client_id,
        "competitor_count": len(competitors),
        "post_frequency": {
            "competitor_avg": round(avg_freq, 1) if avg_freq is not None else None,
            "status": "data_available" if avg_freq is not None else "no_data",
        },
        "engagement_rate": {
            "competitor_avg": round(avg_eng, 2) if avg_eng is not None else None,
            "status": "data_available" if avg_eng is not None else "no_data",
        },
    }
