"""Morning brief and weekly briefing analytics content generation.

Produces structured analytics data for:
1. Morning brief: portfolio grid with sage/amber/coral classification
2. Weekly briefing: per-client trends, top posts, topic resonance, SOV
3. Telegram digest: 3 status-grouped messages

Classification:
- sage (green): healthy, cruising
- amber (yellow): calibrating, warning signs
- coral (red): attention needed, declining
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from sophia.analytics.models import EngagementMetric, KPISnapshot
from sophia.config import Settings

logger = logging.getLogger(__name__)


def generate_morning_brief(db: Session, settings: Settings) -> dict:
    """Produce analytics content for the morning brief.

    Steps:
    a. For each client, get latest KPISnapshot (or compute if stale)
    b. Run detect_client_anomalies for each client
    c. Classify each client: sage/amber/coral
    d. Return portfolio grid, attention flags, summary stats

    Classification:
    - coral: any high-severity anomaly OR engagement_rate declining 3+ weeks
    - amber: any medium anomaly OR approval_rate < 70%
    - sage: otherwise

    Args:
        db: SQLAlchemy session.
        settings: Application settings.

    Returns:
        Dict with portfolio_grid, attention_flags, and summary_stats.
    """
    from sophia.analytics.anomaly import detect_client_anomalies
    from sophia.intelligence.models import Client

    clients = (
        db.query(Client)
        .filter_by(is_archived=False)
        .all()
    )

    portfolio_grid = []
    attention_flags = []
    sage_count = 0
    amber_count = 0
    coral_count = 0

    for client in clients:
        # Get latest KPI snapshot
        kpi = (
            db.query(KPISnapshot)
            .filter_by(client_id=client.id)
            .order_by(KPISnapshot.week_end.desc())
            .first()
        )

        # Get anomalies
        anomalies = detect_client_anomalies(db, client.id)
        anomaly_count = len(anomalies)
        top_anomaly = anomalies[0] if anomalies else None

        # Check engagement trend (declining 3+ weeks)
        engagement_declining = _is_engagement_declining(db, client.id, weeks=3)

        # Classify client
        has_high_severity = any(
            a.get("severity") == "high" for a in anomalies
        )
        has_medium_severity = any(
            a.get("severity") == "medium" for a in anomalies
        )
        low_approval = (
            kpi and kpi.approval_rate is not None and kpi.approval_rate < 70
        )

        if has_high_severity or engagement_declining:
            status_color = "coral"
            coral_count += 1
            attention_flags.append({
                "client_id": client.id,
                "client_name": client.name,
                "reason": (
                    "high-severity anomaly detected"
                    if has_high_severity
                    else "engagement declining 3+ weeks"
                ),
                "anomalies": anomalies,
                "engagement_rate": kpi.engagement_rate if kpi else None,
            })
        elif has_medium_severity or low_approval:
            status_color = "amber"
            amber_count += 1
        else:
            status_color = "sage"
            sage_count += 1

        portfolio_grid.append({
            "client_id": client.id,
            "client_name": client.name,
            "status_color": status_color,
            "engagement_rate": kpi.engagement_rate if kpi else None,
            "follower_growth_pct": kpi.follower_growth_pct if kpi else None,
            "anomaly_count": anomaly_count,
            "top_anomaly": (
                top_anomaly.get("metric_name") if top_anomaly else None
            ),
        })

    return {
        "portfolio_grid": portfolio_grid,
        "attention_flags": attention_flags,
        "summary_stats": {
            "total_clients": len(clients),
            "sage_count": sage_count,
            "amber_count": amber_count,
            "coral_count": coral_count,
        },
    }


def _is_engagement_declining(
    db: Session, client_id: int, weeks: int = 3
) -> bool:
    """Check if engagement rate has been declining for N consecutive weeks.

    Args:
        db: SQLAlchemy session.
        client_id: Client to check.
        weeks: Number of consecutive weeks to check.

    Returns:
        True if engagement declining for N+ weeks.
    """
    snapshots = (
        db.query(KPISnapshot)
        .filter_by(client_id=client_id)
        .order_by(KPISnapshot.week_end.desc())
        .limit(weeks + 1)
        .all()
    )

    if len(snapshots) < weeks + 1:
        return False

    # Check if each week is lower than previous
    for i in range(weeks):
        current = snapshots[i].engagement_rate
        previous = snapshots[i + 1].engagement_rate

        if current is None or previous is None:
            return False
        if current >= previous:
            return False

    return True


def generate_weekly_briefing(db: Session, client_id: int) -> dict:
    """Produce analytics content for weekly strategic briefing per client.

    Includes:
    a. Last 4 weeks KPI trends
    b. Top 5 posts by engagement
    c. Topic resonance analysis (content pillars vs engagement)
    d. Competitor SOV trend
    e. Sophia's improvement metrics (approval_rate, rejection_rate trends)
    f. Industry benchmark comparison

    Args:
        db: SQLAlchemy session.
        client_id: Client for the briefing.

    Returns:
        Structured dict with all sections.
    """
    from sophia.analytics.kpi import compare_to_benchmark, compute_kpi_trends
    from sophia.analytics.sov import compute_share_of_voice

    # a. KPI trends
    trends = compute_kpi_trends(db, client_id, weeks=4)
    trend_data = [
        {
            "week_end": t.week_end.isoformat(),
            "engagement_rate": t.engagement_rate,
            "reach_growth_pct": t.reach_growth_pct,
            "follower_growth_pct": t.follower_growth_pct,
            "save_rate": t.save_rate,
            "share_rate": t.share_rate,
            "approval_rate": t.approval_rate,
            "rejection_rate": t.rejection_rate,
        }
        for t in trends
    ]

    # b. Top 5 posts by engagement
    top_posts = _get_top_posts(db, client_id, limit=5)

    # c. Topic resonance
    topic_resonance = _compute_topic_resonance(db, client_id)

    # d. Competitor SOV
    sov = compute_share_of_voice(db, client_id)

    # e. Improvement metrics
    improvement = _compute_improvement_metrics(trends)

    # f. Benchmark comparison
    latest_kpi = trends[-1] if trends else None
    benchmark = {}
    if latest_kpi:
        benchmark = compare_to_benchmark(db, client_id, latest_kpi)

    return {
        "kpi_trends": trend_data,
        "top_posts": top_posts,
        "topic_resonance": topic_resonance,
        "share_of_voice": sov,
        "improvement_metrics": improvement,
        "benchmark_comparison": benchmark,
    }


def _get_top_posts(db: Session, client_id: int, limit: int = 5) -> list[dict]:
    """Get top posts by total engagement in last 30 days."""
    from sophia.content.models import ContentDraft

    cutoff = date.today() - timedelta(days=30)

    # Get drafts with their total engagement
    drafts = (
        db.query(ContentDraft)
        .filter(
            ContentDraft.client_id == client_id,
            ContentDraft.status == "published",
            ContentDraft.published_at.isnot(None),
        )
        .all()
    )

    post_scores = []
    for draft in drafts:
        engagement = (
            db.query(func.sum(EngagementMetric.metric_value))
            .filter(
                EngagementMetric.content_draft_id == draft.id,
                EngagementMetric.metric_name.in_(
                    ["likes", "comments", "shares", "saved"]
                ),
            )
            .scalar()
        ) or 0

        post_scores.append({
            "draft_id": draft.id,
            "content_pillar": draft.content_pillar,
            "content_format": draft.content_format,
            "platform": draft.platform,
            "published_at": (
                draft.published_at.isoformat() if draft.published_at else None
            ),
            "total_engagement": int(engagement),
        })

    # Sort by engagement descending
    post_scores.sort(key=lambda x: x["total_engagement"], reverse=True)
    return post_scores[:limit]


def _compute_topic_resonance(db: Session, client_id: int) -> list[dict]:
    """Compute which content pillars drive highest engagement."""
    from sophia.content.models import ContentDraft

    drafts = (
        db.query(ContentDraft)
        .filter(
            ContentDraft.client_id == client_id,
            ContentDraft.status == "published",
            ContentDraft.content_pillar.isnot(None),
        )
        .all()
    )

    pillar_data: dict[str, dict] = defaultdict(
        lambda: {"total_engagement": 0, "count": 0}
    )

    for draft in drafts:
        engagement = (
            db.query(func.sum(EngagementMetric.metric_value))
            .filter(
                EngagementMetric.content_draft_id == draft.id,
                EngagementMetric.metric_name.in_(
                    ["likes", "comments", "shares", "saved"]
                ),
            )
            .scalar()
        ) or 0

        pillar = draft.content_pillar
        pillar_data[pillar]["total_engagement"] += int(engagement)
        pillar_data[pillar]["count"] += 1

    result = []
    for pillar, data in pillar_data.items():
        avg_engagement = (
            round(data["total_engagement"] / data["count"], 1)
            if data["count"] > 0
            else 0
        )
        result.append({
            "content_pillar": pillar,
            "post_count": data["count"],
            "total_engagement": data["total_engagement"],
            "avg_engagement_per_post": avg_engagement,
        })

    # Sort by avg engagement descending
    result.sort(key=lambda x: x["avg_engagement_per_post"], reverse=True)
    return result


def _compute_improvement_metrics(trends: list[KPISnapshot]) -> dict:
    """Compute Sophia's improvement metrics from KPI trends.

    Tracks approval_rate and rejection_rate trends to show
    whether Sophia is getting better at producing approvable content.
    """
    if len(trends) < 2:
        return {
            "approval_rate_trend": "insufficient_data",
            "rejection_rate_trend": "insufficient_data",
        }

    first = trends[0]
    last = trends[-1]

    approval_trend = "stable"
    if first.approval_rate is not None and last.approval_rate is not None:
        if last.approval_rate > first.approval_rate + 5:
            approval_trend = "improving"
        elif last.approval_rate < first.approval_rate - 5:
            approval_trend = "declining"

    rejection_trend = "stable"
    if first.rejection_rate is not None and last.rejection_rate is not None:
        if last.rejection_rate < first.rejection_rate - 5:
            rejection_trend = "improving"
        elif last.rejection_rate > first.rejection_rate + 5:
            rejection_trend = "declining"

    return {
        "approval_rate_trend": approval_trend,
        "rejection_rate_trend": rejection_trend,
        "first_week_approval": first.approval_rate,
        "last_week_approval": last.approval_rate,
        "first_week_rejection": first.rejection_rate,
        "last_week_rejection": last.rejection_rate,
    }


def generate_telegram_digest(db: Session) -> list[dict]:
    """Produce 3 Telegram messages grouped by client status.

    1. Attention clients (coral) -- with details and anomalies
    2. Calibrating clients (amber) -- summaries
    3. Cruising clients (sage) -- all-clear list

    Args:
        db: SQLAlchemy session.

    Returns:
        List of 3 dicts with {group: str, clients: list, summary: str}.
    """
    from sophia.analytics.anomaly import detect_client_anomalies
    from sophia.intelligence.models import Client

    clients = (
        db.query(Client)
        .filter_by(is_archived=False)
        .all()
    )

    coral_clients = []
    amber_clients = []
    sage_clients = []

    for client in clients:
        kpi = (
            db.query(KPISnapshot)
            .filter_by(client_id=client.id)
            .order_by(KPISnapshot.week_end.desc())
            .first()
        )

        anomalies = detect_client_anomalies(db, client.id)
        has_high = any(a.get("severity") == "high" for a in anomalies)
        has_medium = any(a.get("severity") == "medium" for a in anomalies)
        engagement_declining = _is_engagement_declining(db, client.id)
        low_approval = (
            kpi and kpi.approval_rate is not None and kpi.approval_rate < 70
        )

        client_info = {
            "client_id": client.id,
            "client_name": client.name,
            "engagement_rate": kpi.engagement_rate if kpi else None,
            "anomaly_count": len(anomalies),
        }

        if has_high or engagement_declining:
            client_info["anomalies"] = anomalies
            coral_clients.append(client_info)
        elif has_medium or low_approval:
            amber_clients.append(client_info)
        else:
            sage_clients.append(client_info)

    return [
        {
            "group": "attention",
            "clients": coral_clients,
            "summary": (
                f"{len(coral_clients)} client(s) need attention"
                if coral_clients
                else "No clients need immediate attention"
            ),
        },
        {
            "group": "calibrating",
            "clients": amber_clients,
            "summary": (
                f"{len(amber_clients)} client(s) calibrating"
                if amber_clients
                else "No clients in calibration"
            ),
        },
        {
            "group": "cruising",
            "clients": sage_clients,
            "summary": (
                f"{len(sage_clients)} client(s) cruising"
                if sage_clients
                else "No clients cruising"
            ),
        },
    ]
