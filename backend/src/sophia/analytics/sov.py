"""Share of voice scoring against competitor data.

Computes a client's share of voice relative to tracked competitors
using engagement metrics and posting frequency from CompetitorSnapshot.
Trend is computed by comparing current vs previous 30-day periods.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from sophia.analytics.models import EngagementMetric
from sophia.research.models import Competitor, CompetitorSnapshot

logger = logging.getLogger(__name__)


def compute_share_of_voice(db: Session, client_id: int) -> dict:
    """Compute share of voice for a client relative to competitors.

    SOV = (client_engagement + client_post_count)
          / (client + sum(competitor engagement + post counts))

    Trend is computed by comparing current 30-day SOV vs previous 30-day SOV.

    Args:
        db: SQLAlchemy session.
        client_id: Client to compute SOV for.

    Returns:
        Dict with sov_score (0-1), client_engagement, competitor_data,
        and trend ("up"/"down"/"stable").
    """
    today = date.today()
    current_start = today - timedelta(days=30)
    prev_start = current_start - timedelta(days=30)

    # Client engagement (current 30 days)
    client_engagement = _get_client_engagement(
        db, client_id, current_start, today
    )
    client_post_count = _get_client_post_count(
        db, client_id, current_start, today
    )

    # Get competitor data from latest snapshots
    competitors = (
        db.query(Competitor)
        .filter(
            Competitor.client_id == client_id,
            Competitor.is_primary == 1,
        )
        .all()
    )

    competitor_data = []
    total_competitor_score = 0.0

    for comp in competitors:
        # Get latest snapshot
        snapshot = (
            db.query(CompetitorSnapshot)
            .filter_by(competitor_id=comp.id)
            .order_by(CompetitorSnapshot.id.desc())
            .first()
        )

        if snapshot:
            # Use engagement rate * frequency as engagement proxy
            comp_engagement = (snapshot.avg_engagement_rate or 0) * 100
            comp_posts = snapshot.post_frequency_7d or 0
            comp_score = comp_engagement + comp_posts

            competitor_data.append({
                "name": comp.name,
                "engagement": round(comp_engagement, 1),
                "post_count": comp_posts,
            })
            total_competitor_score += comp_score
        else:
            competitor_data.append({
                "name": comp.name,
                "engagement": 0,
                "post_count": 0,
            })

    # Compute SOV
    client_score = client_engagement + client_post_count
    total_score = client_score + total_competitor_score

    sov_score = round(client_score / total_score, 3) if total_score > 0 else 0.0

    # Compute trend (compare to previous period)
    prev_engagement = _get_client_engagement(
        db, client_id, prev_start, current_start
    )
    prev_post_count = _get_client_post_count(
        db, client_id, prev_start, current_start
    )
    prev_client_score = prev_engagement + prev_post_count
    prev_total = prev_client_score + total_competitor_score

    prev_sov = round(prev_client_score / prev_total, 3) if prev_total > 0 else 0.0

    if sov_score > prev_sov + 0.01:
        trend = "up"
    elif sov_score < prev_sov - 0.01:
        trend = "down"
    else:
        trend = "stable"

    return {
        "sov_score": sov_score,
        "client_engagement": round(client_engagement, 1),
        "client_post_count": client_post_count,
        "competitor_data": competitor_data,
        "trend": trend,
    }


def _get_client_engagement(
    db: Session, client_id: int, start: date, end: date
) -> float:
    """Get total engagement metric values for a client in date range."""
    result = (
        db.query(func.sum(EngagementMetric.metric_value))
        .filter(
            EngagementMetric.client_id == client_id,
            EngagementMetric.metric_name.in_(
                ["likes", "comments", "shares", "saved"]
            ),
            EngagementMetric.metric_date >= start,
            EngagementMetric.metric_date <= end,
        )
        .scalar()
    )
    return float(result) if result else 0.0


def _get_client_post_count(
    db: Session, client_id: int, start: date, end: date
) -> int:
    """Get count of published posts for a client in date range."""
    from sophia.content.models import ContentDraft

    count = (
        db.query(ContentDraft)
        .filter(
            ContentDraft.client_id == client_id,
            ContentDraft.status == "published",
            ContentDraft.published_at.isnot(None),
        )
        .count()
    )
    return count
