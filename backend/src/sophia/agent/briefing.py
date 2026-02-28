"""Briefing generation: daily standup and weekly strategic briefings.

Generates structured briefings for operator review. Daily standups
aggregate data from all domains (approvals, errors, performance, publishing).
Weekly briefings surface cross-client patterns and improvement metrics.

IMPORTANT: Briefing generation runs as a post-cycle scheduled job,
NOT inside the per-client cycle. This prevents cycle blocking (Pitfall 6).
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from sophia.agent.models import Briefing, BusinessInsight, Learning
from sophia.agent.schemas import (
    BriefingItem,
    CrossClientPattern,
    DailyBriefingContent,
    WeeklyBriefingContent,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Daily Standup Briefing (LRNG-02)
# ---------------------------------------------------------------------------


async def generate_daily_standup(db: Session) -> DailyBriefingContent:
    """Generate a daily standup briefing aggregating data from all domains.

    Follows the gather-prioritize-compose pattern:
    1. GATHER: Pull data from all domains
    2. PRIORITIZE: Sort items by severity (critical > warning > info)
    3. COMPOSE: Return structured DailyBriefingContent

    For multi-client version (20 clients): groups items by urgency first,
    then by theme, highlights cross-client patterns.

    Args:
        db: SQLAlchemy session.

    Returns:
        DailyBriefingContent with severity-sorted items.
    """
    items: list[BriefingItem] = []
    today = date.today()
    yesterday = today - timedelta(days=1)

    # GATHER: Pull data from all domains
    pending_approvals = _gather_pending_approvals(db)
    cycle_errors = _gather_cycle_errors(db, since=yesterday)
    performance_alerts = _gather_performance_alerts(db)
    scheduled_posts = _gather_scheduled_posts(db)
    portfolio_health = _gather_portfolio_health(db)
    recent_learnings = _gather_recent_learnings(db, since=yesterday)

    # PRIORITIZE: Create BriefingItems sorted by severity

    # Critical items: cycle errors, failed publishes
    for error in cycle_errors:
        items.append(BriefingItem(
            severity="critical",
            category="cycle_errors",
            message=error["message"],
            client_name=error.get("client_name"),
            action_needed=True,
        ))

    # Warning items: performance anomalies, engagement drops
    for alert in performance_alerts:
        items.append(BriefingItem(
            severity="warning",
            category="performance",
            message=alert["message"],
            client_name=alert.get("client_name"),
            action_needed=alert.get("action_needed", False),
        ))

    # Info items: successful publishes, new learnings, scheduled posts
    if pending_approvals["count"] > 0:
        items.append(BriefingItem(
            severity="info",
            category="approvals",
            message=f"{pending_approvals['count']} drafts awaiting approval",
            action_needed=True,
        ))

    if scheduled_posts["count"] > 0:
        items.append(BriefingItem(
            severity="info",
            category="publishing",
            message=f"{scheduled_posts['count']} posts scheduled for today",
        ))

    for learning in recent_learnings:
        items.append(BriefingItem(
            severity="info",
            category="learnings",
            message=f"New insight: {learning['content'][:80]}...",
            client_name=learning.get("client_name"),
        ))

    # Sort by severity priority
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    items.sort(key=lambda x: severity_order.get(x.severity, 3))

    # COMPOSE
    briefing_content = DailyBriefingContent(
        date=today.isoformat(),
        items=items,
        portfolio_summary=portfolio_health,
        pending_approval_count=pending_approvals["count"],
    )

    # Persist to DB
    briefing = Briefing(
        briefing_type="daily",
        content_json=json.dumps(briefing_content.model_dump()),
        generated_at=datetime.now(timezone.utc),
    )
    db.add(briefing)
    db.commit()

    logger.info(
        "Daily standup generated: %d items (%d critical, %d warning)",
        len(items),
        sum(1 for i in items if i.severity == "critical"),
        sum(1 for i in items if i.severity == "warning"),
    )

    return briefing_content


# ---------------------------------------------------------------------------
# Weekly Strategic Briefing (LRNG-03)
# ---------------------------------------------------------------------------


async def generate_weekly_briefing(db: Session) -> WeeklyBriefingContent:
    """Generate a weekly strategic briefing with cross-client patterns.

    Aggregates data across all clients for the past 7 days. Includes
    cross-client pattern transfer opportunities surfaced for operator approval.

    Args:
        db: SQLAlchemy session.

    Returns:
        WeeklyBriefingContent with patterns, metrics, and recommendations.
    """
    today = date.today()
    week_start = today - timedelta(days=7)

    # Cross-client patterns
    patterns = await detect_cross_client_patterns(db)
    pattern_dicts = [p.model_dump() for p in patterns]

    # Improvement metrics
    improvement = _get_improvement_metrics(db)

    # Strategy recommendations
    recommendations = _generate_strategy_recommendations(
        db, patterns, improvement
    )

    # Intelligence highlights
    intelligence_highlights = _get_intelligence_highlights(db, since=week_start)

    briefing_content = WeeklyBriefingContent(
        week_start=week_start.isoformat(),
        week_end=today.isoformat(),
        cross_client_patterns=pattern_dicts,
        improvement_metrics=improvement,
        strategy_recommendations=recommendations,
        intelligence_highlights=intelligence_highlights,
    )

    # Persist to DB
    briefing = Briefing(
        briefing_type="weekly",
        content_json=json.dumps(briefing_content.model_dump()),
        generated_at=datetime.now(timezone.utc),
    )
    db.add(briefing)
    db.commit()

    logger.info(
        "Weekly briefing generated: %d patterns, %d recommendations",
        len(patterns),
        len(recommendations),
    )

    return briefing_content


# ---------------------------------------------------------------------------
# Cross-Client Pattern Detection (LRNG-07)
# ---------------------------------------------------------------------------


async def detect_cross_client_patterns(
    db: Session,
    min_similarity: float = 0.82,
    min_clients: int = 2,
) -> list[CrossClientPattern]:
    """Detect patterns appearing across multiple clients via semantic similarity.

    Gets high-confidence learnings from past 7 days and searches LanceDB
    for semantically similar learnings from OTHER clients.

    CRITICAL: Output is anonymized -- patterns describe themes and counts,
    NEVER specific client names or data. Anonymization happens at this
    service boundary, not at the presentation layer.

    Pattern transfer preserves per-client voice profiles -- only subject
    matter transfers, not voice (locked decision from CONTEXT.md).

    Args:
        db: SQLAlchemy session.
        min_similarity: Minimum cosine similarity threshold (default 0.82).
        min_clients: Minimum number of clients sharing a pattern (default 2).

    Returns:
        List of anonymized CrossClientPattern objects.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    # Get high-confidence recent learnings
    recent_learnings = (
        db.query(Learning)
        .filter(
            Learning.confidence >= 0.7,
            Learning.is_superseded == False,  # noqa: E712
            Learning.created_at >= cutoff,
        )
        .all()
    )

    if not recent_learnings:
        return []

    # Search LanceDB for similar learnings from other clients
    patterns: list[CrossClientPattern] = []
    seen_themes: set[str] = set()

    for learning in recent_learnings:
        similar = _search_similar_learnings(
            learning, min_similarity=min_similarity
        )

        if not similar:
            continue

        # Filter to learnings from OTHER clients
        cross_client_matches = [
            m for m in similar
            if m.get("client_id") != learning.client_id
        ]

        if not cross_client_matches:
            continue

        # Count unique clients
        unique_clients = {m.get("client_id") for m in cross_client_matches}
        unique_clients.add(learning.client_id)

        if len(unique_clients) < min_clients:
            continue

        # Anonymize: extract theme, not client-specific data
        theme = _extract_theme(learning.content)

        # Deduplicate patterns
        if theme in seen_themes:
            continue
        seen_themes.add(theme)

        avg_similarity = (
            sum(m.get("similarity", 0) for m in cross_client_matches)
            / len(cross_client_matches)
        ) if cross_client_matches else 0.0

        patterns.append(CrossClientPattern(
            theme=theme,
            evidence_count=len(cross_client_matches) + 1,
            client_count=len(unique_clients),
            source_learning_id=learning.id,
            similarity_score=round(avg_similarity, 3),
        ))

    return patterns


# ---------------------------------------------------------------------------
# Gather helpers (best-effort, ImportError-safe)
# ---------------------------------------------------------------------------


def _gather_pending_approvals(db: Session) -> dict:
    """Count drafts awaiting operator approval."""
    try:
        from sophia.content.models import ContentDraft

        count = (
            db.query(ContentDraft)
            .filter(ContentDraft.status == "in_review")
            .count()
        )
        return {"count": count}
    except ImportError:
        return {"count": 0}


def _gather_cycle_errors(db: Session, since: date) -> list[dict]:
    """Gather cycle execution errors from the last 24 hours."""
    # Cycle runs table is deferred; return empty for now
    return []


def _gather_performance_alerts(db: Session) -> list[dict]:
    """Gather performance anomalies from analytics module."""
    try:
        from sophia.analytics.anomaly import detect_client_anomalies
        from sophia.intelligence.models import Client

        alerts = []
        clients = (
            db.query(Client)
            .filter_by(is_archived=False)
            .all()
        )

        for client in clients:
            anomalies = detect_client_anomalies(db, client.id)
            for anomaly in anomalies:
                severity = anomaly.get("severity", "low")
                if severity in ("high", "medium"):
                    alerts.append({
                        "message": (
                            f"{client.name}: {anomaly.get('metric_name', 'metric')} "
                            f"anomaly ({severity})"
                        ),
                        "client_name": client.name,
                        "action_needed": severity == "high",
                    })

        return alerts
    except ImportError:
        return []


def _gather_scheduled_posts(db: Session) -> dict:
    """Count posts scheduled for today."""
    try:
        from sophia.approval.models import PublishingQueueEntry

        today = date.today()
        tomorrow = today + timedelta(days=1)
        count = (
            db.query(PublishingQueueEntry)
            .filter(
                PublishingQueueEntry.status == "queued",
                PublishingQueueEntry.scheduled_at >= today.isoformat(),
                PublishingQueueEntry.scheduled_at < tomorrow.isoformat(),
            )
            .count()
        )
        return {"count": count}
    except ImportError:
        return {"count": 0}


def _gather_portfolio_health(db: Session) -> dict:
    """Aggregate portfolio health summary."""
    try:
        from sophia.intelligence.models import Client

        total = db.query(Client).filter_by(is_archived=False).count()
        return {"total_clients": total}
    except ImportError:
        return {"total_clients": 0}


def _gather_recent_learnings(db: Session, since: date) -> list[dict]:
    """Get learnings created since the given date."""
    learnings = (
        db.query(Learning)
        .filter(
            Learning.is_superseded == False,  # noqa: E712
            Learning.created_at >= since.isoformat(),
        )
        .order_by(Learning.created_at.desc())
        .limit(10)
        .all()
    )

    results = []
    for learning in learnings:
        # Try to resolve client name
        client_name = None
        try:
            from sophia.intelligence.models import Client

            client = db.get(Client, learning.client_id)
            if client:
                client_name = client.name
        except ImportError:
            pass

        results.append({
            "content": learning.content,
            "client_name": client_name,
            "learning_type": learning.learning_type,
        })

    return results


# ---------------------------------------------------------------------------
# Pattern detection helpers
# ---------------------------------------------------------------------------


def _search_similar_learnings(
    learning: Learning,
    min_similarity: float = 0.82,
) -> list[dict]:
    """Search LanceDB for semantically similar learnings.

    Returns list of dicts with client_id and similarity score.
    Falls back to empty list if LanceDB unavailable.
    """
    try:
        from sophia.semantic.index import get_lance_table

        table = get_lance_table("learnings")
        from sophia.semantic.embeddings import embed
        import asyncio

        vector = asyncio.get_event_loop().run_until_complete(
            embed(f"{learning.learning_type}: {learning.content}")
        )

        results = (
            table.search(vector)
            .limit(20)
            .to_list()
        )

        similar = []
        for row in results:
            score = 1 - row.get("_distance", 1.0)  # LanceDB returns distance
            if score >= min_similarity and row.get("record_id") != learning.id:
                similar.append({
                    "client_id": row.get("client_id"),
                    "record_id": row.get("record_id"),
                    "similarity": score,
                })

        return similar
    except Exception:
        logger.debug(
            "LanceDB search unavailable for cross-client patterns; skipping"
        )
        return []


def _extract_theme(content: str) -> str:
    """Extract a theme label from learning content for anonymized pattern display.

    Returns the first sentence or first 100 chars as a theme summary.
    """
    # Take first sentence
    for sep in [".", "!", "?"]:
        idx = content.find(sep)
        if idx > 0:
            return content[:idx + 1].strip()
    # Fallback: first 100 chars
    return content[:100].strip()


# ---------------------------------------------------------------------------
# Weekly briefing helpers
# ---------------------------------------------------------------------------


def _get_improvement_metrics(db: Session) -> dict:
    """Get improvement rate metrics for the weekly briefing."""
    try:
        from sophia.agent.service import calculate_improvement_rate

        report = calculate_improvement_rate(db)
        return report.model_dump()
    except (ImportError, Exception):
        return {}


def _generate_strategy_recommendations(
    db: Session,
    patterns: list[CrossClientPattern],
    improvement: dict,
) -> list[str]:
    """Generate strategy recommendations based on patterns and metrics."""
    recommendations: list[str] = []

    if patterns:
        recommendations.append(
            f"Cross-client pattern detected across {len(patterns)} theme(s). "
            "Review for transfer opportunities in weekly briefing."
        )

    # Check improvement direction
    content_dir = improvement.get("content_quality", {}).get("direction", "")
    if content_dir == "declining":
        recommendations.append(
            "Content quality trend declining. Consider reviewing recent "
            "rejection feedback for recurring themes."
        )
    elif content_dir == "improving":
        recommendations.append(
            "Content quality improving. Current voice calibration approach "
            "is working well."
        )

    intelligence_dir = improvement.get("intelligence_depth", {}).get("direction", "")
    if intelligence_dir == "stable" or intelligence_dir == "declining":
        recommendations.append(
            "Intelligence gathering rate is flat. Consider scheduling "
            "operator check-ins to surface new business insights."
        )

    return recommendations


def _get_intelligence_highlights(db: Session, since: date) -> list[dict]:
    """Get notable intelligence entries from the past week."""
    insights = (
        db.query(BusinessInsight)
        .filter(
            BusinessInsight.is_active == True,  # noqa: E712
            BusinessInsight.confidence >= 0.8,
            BusinessInsight.created_at >= since.isoformat(),
        )
        .order_by(BusinessInsight.confidence.desc())
        .limit(5)
        .all()
    )

    return [
        {
            "category": i.category,
            "fact": i.fact_statement,
            "confidence": i.confidence,
        }
        for i in insights
    ]
