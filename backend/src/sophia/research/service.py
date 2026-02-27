"""Research orchestration: daily cycle per client, finding creation, digest generation.

Runs the daily research cycle by querying MCP sources scoped to each client's
market, creates structured findings with confidence scores and content angles,
and generates daily digests with freshness metrics and source health.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from sophia.intelligence.models import Client
from sophia.research.models import (
    DECAY_WINDOWS,
    FindingType,
    ResearchFinding,
    relevance_score,
)
from sophia.research.schemas import FindingResponse, ResearchDigest
from sophia.research.sources import MCPSourceRegistry, ResearchScope

logger = logging.getLogger(__name__)


def _finding_to_response(finding: ResearchFinding) -> FindingResponse:
    """Convert a ResearchFinding ORM object to a FindingResponse schema."""
    # Compute live relevance score
    created = finding.created_at
    if created and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)

    rel_score = (
        relevance_score(FindingType(finding.finding_type.value), created)
        if created
        else 0.0
    )

    return FindingResponse(
        id=finding.id,
        client_id=finding.client_id,
        finding_type=finding.finding_type.value if hasattr(finding.finding_type, "value") else str(finding.finding_type),
        topic=finding.topic,
        summary=finding.summary,
        content_angles=finding.content_angles or [],
        source_url=finding.source_url,
        source_name=finding.source_name,
        relevance_score=rel_score,
        confidence=finding.confidence,
        is_time_sensitive=bool(finding.is_time_sensitive),
        created_at=finding.created_at,
        expires_at=finding.expires_at,
    )


async def run_research_cycle(
    db: Session,
    client_id: int,
    source_registry: Optional[MCPSourceRegistry] = None,
) -> ResearchDigest:
    """Execute the daily research cycle for one client.

    Steps:
    1. Load client profile and build ResearchScope
    2. Query available MCP sources using scoped queries
    3. Distill raw results into structured ResearchFinding records
    4. Compute expires_at from FindingType decay window
    5. Flag time-sensitive findings (events within 48 hours)
    6. Save to SQLite, then write-through sync to LanceDB
    7. Feed relevant findings into intelligence service
    8. Generate and return ResearchDigest

    Args:
        db: SQLAlchemy session.
        client_id: Client to research.
        source_registry: Optional MCP source registry (injectable for testing).

    Returns:
        ResearchDigest with all findings from this cycle.
    """
    from sophia.intelligence.service import ClientService

    client = ClientService.get_client(db, client_id)
    scope = ResearchScope(client)

    if source_registry is None:
        source_registry = MCPSourceRegistry()

    now = datetime.now(timezone.utc)
    findings: list[ResearchFinding] = []

    # Build research topics from content pillars and industry
    topics = _build_research_topics(scope)

    # Query each source type
    for topic in topics:
        # Local news
        news_results = await source_registry.query_source(
            "google-news-trends",
            scope.scoped_news_query(topic),
            scope=scope,
        )
        if news_results:
            for raw in news_results:
                finding = _create_finding_from_raw(
                    db, client_id, FindingType.NEWS, raw, now
                )
                if finding:
                    findings.append(finding)

        # Community discussions
        community_results = await source_registry.query_source(
            "reddit",
            scope.scoped_community_query(topic),
            scope=scope,
        )
        if community_results:
            for raw in community_results:
                finding = _create_finding_from_raw(
                    db, client_id, FindingType.COMMUNITY, raw, now
                )
                if finding:
                    findings.append(finding)

    # Google Trends (not topic-specific)
    trends_results = await source_registry.query_source(
        "google-news-trends",
        scope.scoped_trends_query(),
        scope=scope,
    )
    if trends_results:
        for raw in trends_results:
            finding = _create_finding_from_raw(
                db, client_id, FindingType.TREND, raw, now
            )
            if finding:
                findings.append(finding)

    # Commit all findings to SQLite
    if findings:
        db.commit()

        # Write-through sync to LanceDB for each finding
        for finding in findings:
            db.refresh(finding)
            await _sync_finding_to_lance(finding)

        # Feed relevant findings into intelligence enrichment
        await _feed_intelligence(db, client_id, findings)

    # Generate and return digest
    digest = generate_daily_digest(db, client_id, source_registry=source_registry)
    return digest


def _build_research_topics(scope: ResearchScope) -> list[str]:
    """Build research topics from client's content pillars and industry.

    Targets 3-5 focused topics per cycle, prioritizing content pillars.
    When pillars are thin, falls back to industry-level topics.
    """
    topics: list[str] = []

    # Content pillars are primary research targets
    if scope.content_pillars:
        topics.extend(scope.content_pillars[:3])

    # Add industry as fallback/supplement
    if scope.industry and len(topics) < 3:
        topics.append(scope.industry)

    # Ensure at least one topic
    if not topics:
        topics.append(scope.industry or "local business")

    return topics[:5]  # Cap at 5 per cycle


def _create_finding_from_raw(
    db: Session,
    client_id: int,
    finding_type: FindingType,
    raw: dict,
    now: datetime,
) -> Optional[ResearchFinding]:
    """Create a ResearchFinding from raw MCP query result.

    Extracts topic, summary, content angles, source attribution.
    Computes confidence score and expiry from decay window.
    Flags time-sensitive findings (events within 48 hours).

    Args:
        db: SQLAlchemy session.
        client_id: Client ID.
        finding_type: Type of finding (determines decay).
        raw: Raw result dict from MCP source.
        now: Current timestamp.

    Returns:
        ResearchFinding ORM object (added to session but not committed), or None if invalid.
    """
    topic = raw.get("title", raw.get("topic", ""))
    summary = raw.get("summary", raw.get("description", raw.get("text", "")))

    if not topic or not summary:
        return None

    # Extract content angles (1-2 per finding)
    angles = raw.get("content_angles", [])
    if not angles:
        # Generate basic angle from topic
        angles = [f"Share insights about {topic}"]

    # Confidence based on source reliability and data richness
    confidence = _compute_confidence(raw)

    # Compute expiry from decay window
    decay_window = DECAY_WINDOWS[finding_type]
    expires_at = now + decay_window

    # Time-sensitive: events within 48 hours
    event_date = raw.get("event_date")
    is_time_sensitive = 0
    if event_date:
        try:
            if isinstance(event_date, str):
                event_dt = datetime.fromisoformat(event_date)
                if event_dt.tzinfo is None:
                    event_dt = event_dt.replace(tzinfo=timezone.utc)
            else:
                event_dt = event_date
            if (event_dt - now) <= timedelta(hours=48):
                is_time_sensitive = 1
        except (ValueError, TypeError):
            pass

    finding = ResearchFinding(
        client_id=client_id,
        finding_type=finding_type,
        topic=topic,
        summary=summary,
        content_angles=angles[:2],  # Cap at 2 angles
        source_url=raw.get("url", raw.get("source_url")),
        source_name=raw.get("source_name", raw.get("source", "unknown")),
        relevance_score_val=1.0,  # Fresh finding starts at full relevance
        confidence=confidence,
        is_time_sensitive=is_time_sensitive,
        expires_at=expires_at,
    )
    db.add(finding)
    return finding


def _compute_confidence(raw: dict) -> float:
    """Compute confidence score based on source count and reliability.

    Higher confidence for results with multiple sources or from trusted sources.
    """
    confidence = 0.5  # Base confidence

    # Source count bonus
    source_count = raw.get("source_count", 1)
    if source_count >= 3:
        confidence += 0.3
    elif source_count >= 2:
        confidence += 0.15

    # Trusted source bonus
    trusted_sources = {"reuters", "cbc", "globalnews", "thestar", "ctvnews"}
    source_name = raw.get("source_name", raw.get("source", "")).lower()
    if any(trusted in source_name for trusted in trusted_sources):
        confidence += 0.2

    return min(1.0, confidence)


async def _sync_finding_to_lance(finding: ResearchFinding) -> None:
    """Write-through sync a research finding to LanceDB."""
    try:
        from sophia.semantic.sync import sync_to_lance

        await sync_to_lance(
            record_type="research_findings",
            record_id=finding.id,
            text=f"{finding.topic}: {finding.summary}",
            metadata={
                "client_id": finding.client_id,
                "domain": finding.finding_type.value if hasattr(finding.finding_type, "value") else str(finding.finding_type),
                "created_at": (
                    finding.created_at.isoformat()
                    if finding.created_at
                    else datetime.now(timezone.utc).isoformat()
                ),
            },
        )
    except Exception:
        logger.exception(
            "Write-through sync failed for research finding %d",
            finding.id,
        )


async def _feed_intelligence(
    db: Session,
    client_id: int,
    findings: list[ResearchFinding],
) -> None:
    """Feed research findings into the intelligence enrichment service.

    Converts relevant findings into intelligence entries to progressively
    enrich client profiles.
    """
    try:
        from sophia.intelligence.models import IntelligenceDomain
        from sophia.intelligence.service import add_intelligence

        domain_map = {
            FindingType.NEWS: IntelligenceDomain.INDUSTRY,
            FindingType.TREND: IntelligenceDomain.INDUSTRY,
            FindingType.INDUSTRY: IntelligenceDomain.INDUSTRY,
            FindingType.COMMUNITY: IntelligenceDomain.CUSTOMERS,
        }

        for finding in findings:
            if finding.confidence >= 0.6:  # Only high-confidence findings
                domain = domain_map.get(
                    FindingType(finding.finding_type.value)
                    if hasattr(finding.finding_type, "value")
                    else finding.finding_type,
                    IntelligenceDomain.INDUSTRY,
                )
                await add_intelligence(
                    db=db,
                    client_id=client_id,
                    domain=domain,
                    fact=f"{finding.topic}: {finding.summary}",
                    source=f"research:finding:{finding.id}",
                    confidence=finding.confidence,
                )
    except Exception:
        logger.exception(
            "Failed to feed findings into intelligence for client %d",
            client_id,
        )


def get_findings_for_content(
    db: Session,
    client_id: int,
    limit: int = 20,
    finding_type: Optional[str] = None,
    min_relevance: float = 0.0,
) -> list[ResearchFinding]:
    """Query findings for content generation.

    Filters by:
    - Client scope (SAFE-01)
    - Not expired (relevance_score > 0.0)
    - Optional finding_type filter
    - Minimum relevance threshold

    Sorts by relevance_score * confidence descending.
    Excludes findings from blocked sources.

    Args:
        db: SQLAlchemy session.
        client_id: Client ID.
        limit: Maximum findings to return.
        finding_type: Optional type filter.
        min_relevance: Minimum relevance score threshold.

    Returns:
        List of ResearchFinding objects sorted by relevance*confidence.
    """
    from sophia.intelligence.models import Client

    now = datetime.now(timezone.utc)

    query = db.query(ResearchFinding).filter(
        ResearchFinding.client_id == client_id,
        ResearchFinding.expires_at > now,  # Not expired
    )

    if finding_type:
        query = query.filter(
            ResearchFinding.finding_type == FindingType(finding_type)
        )

    findings = query.all()

    # Load client for blocklist check
    client = db.query(Client).filter(Client.id == client_id).first()
    scope = ResearchScope(client) if client else None

    # Filter and score
    scored: list[tuple[float, ResearchFinding]] = []
    for f in findings:
        # Compute live relevance
        created = f.created_at
        if created and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)

        rel = relevance_score(
            FindingType(f.finding_type.value)
            if hasattr(f.finding_type, "value")
            else f.finding_type,
            created,
        ) if created else 0.0

        if rel <= min_relevance:
            continue

        # Check blocklist
        if scope and scope.is_blocked(f.source_url or ""):
            continue

        composite = rel * f.confidence
        scored.append((composite, f))

    # Sort by composite score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    return [f for _, f in scored[:limit]]


def generate_daily_digest(
    db: Session,
    client_id: int,
    source_registry: Optional[MCPSourceRegistry] = None,
) -> ResearchDigest:
    """Assemble daily digest with findings grouped by type.

    Includes:
    - Per-client findings grouped by type (news, trends, community, competitor)
    - Time-sensitive alerts at top
    - Research freshness metric: % of findings within decay window
    - Source health: which MCP sources available vs circuit breaker open

    Args:
        db: SQLAlchemy session.
        client_id: Client ID.
        source_registry: Optional registry for source health report.

    Returns:
        ResearchDigest with all current findings.
    """
    now = datetime.now(timezone.utc)

    # Get all findings for this client
    all_findings = (
        db.query(ResearchFinding)
        .filter(ResearchFinding.client_id == client_id)
        .order_by(ResearchFinding.created_at.desc())
        .all()
    )

    # Group by type
    findings_by_type: dict[str, list[FindingResponse]] = {}
    time_sensitive_alerts: list[FindingResponse] = []
    fresh_count = 0
    total_count = len(all_findings)

    for finding in all_findings:
        response = _finding_to_response(finding)

        # Check freshness based on expires_at (authoritative expiry)
        is_fresh = False
        if finding.expires_at is not None:
            exp = finding.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            is_fresh = exp > now
        elif response.relevance_score > 0.0:
            # No expiry set -- consider fresh if relevance > 0
            is_fresh = True
        if is_fresh:
            fresh_count += 1

        # Group by type
        ftype = response.finding_type
        if ftype not in findings_by_type:
            findings_by_type[ftype] = []
        findings_by_type[ftype].append(response)

        # Time-sensitive alerts
        if response.is_time_sensitive:
            time_sensitive_alerts.append(response)

    # Freshness percentage
    freshness_pct = (fresh_count / total_count * 100) if total_count > 0 else 0.0

    # Source health
    source_health = {}
    if source_registry:
        source_health = source_registry.get_health_report()

    return ResearchDigest(
        client_id=client_id,
        generated_at=now,
        findings_by_type=findings_by_type,
        time_sensitive_alerts=time_sensitive_alerts,
        research_freshness_pct=round(freshness_pct, 1),
        source_health=source_health,
        total_findings=total_count,
    )
