"""Agent service: improvement rate calculation and intelligence report generation.

Provides the self-measurement capabilities that demonstrate Sophia's
compounding value over time.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from sophia.agent.models import BusinessInsight, Learning
from sophia.agent.schemas import (
    ImprovementReport,
    IntelligenceReport,
    TrendMetric,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Improvement Rate Calculation (LRNG-05)
# ---------------------------------------------------------------------------


def calculate_improvement_rate(
    db: Session,
    weeks_back: int = 4,
) -> ImprovementReport:
    """Calculate Sophia's self-improvement rate across three metric categories.

    Category 1 -- Content quality: weekly approval rate trend, weekly edit
    frequency trend (decreasing edit rate = improving).

    Category 2 -- Decision quality: average decision quality score per week
    (from evaluation pipeline in phase 5).

    Category 3 -- Intelligence depth: learning count per week, unique pattern
    connections per week (growing = improving).

    For each category, calculates week-over-week deltas to determine
    trend direction.

    Args:
        db: SQLAlchemy session.
        weeks_back: Number of weeks to analyze (default 4).

    Returns:
        ImprovementReport with trend metrics for each category.
    """
    today = date.today()

    # Content quality: approval rate per week
    content_values = _weekly_approval_rates(db, today, weeks_back)
    content_quality = TrendMetric(
        values=content_values,
        direction=_trend_direction(content_values),
    )

    # Decision quality: average quality score per week
    decision_values = _weekly_decision_quality(db, today, weeks_back)
    decision_quality = TrendMetric(
        values=decision_values,
        direction=_trend_direction(decision_values),
    )

    # Intelligence depth: learning count per week
    intelligence_values = _weekly_learning_counts(db, today, weeks_back)
    intelligence_depth = TrendMetric(
        values=intelligence_values,
        direction=_trend_direction(intelligence_values),
    )

    return ImprovementReport(
        content_quality=content_quality,
        decision_quality=decision_quality,
        intelligence_depth=intelligence_depth,
    )


def _trend_direction(values: list[float]) -> str:
    """Determine trend direction from a list of weekly values.

    Uses simple linear regression slope:
    - slope > 0.05: "improving"
    - slope < -0.05: "declining"
    - otherwise: "stable"
    - < 2 data points: "insufficient_data"

    Args:
        values: List of weekly metric values (oldest first).

    Returns:
        One of: "improving", "declining", "stable", "insufficient_data".
    """
    if len(values) < 2:
        return "insufficient_data"

    n = len(values)
    x_sum = sum(range(n))
    y_sum = sum(values)
    xy_sum = sum(i * v for i, v in enumerate(values))
    x2_sum = sum(i * i for i in range(n))

    denominator = n * x2_sum - x_sum * x_sum
    if denominator == 0:
        return "stable"

    slope = (n * xy_sum - x_sum * y_sum) / denominator

    if slope > 0.05:
        return "improving"
    elif slope < -0.05:
        return "declining"
    else:
        return "stable"


def _weekly_approval_rates(
    db: Session, today: date, weeks_back: int
) -> list[float]:
    """Compute weekly approval rates (approved / total reviewed)."""
    values = []
    try:
        from sophia.content.models import ContentDraft

        for w in range(weeks_back, 0, -1):
            week_end = today - timedelta(weeks=w - 1)
            week_start = week_end - timedelta(days=7)

            total = (
                db.query(ContentDraft)
                .filter(
                    ContentDraft.status.in_(
                        ["approved", "rejected", "published"]
                    ),
                    ContentDraft.updated_at >= week_start.isoformat(),
                    ContentDraft.updated_at < week_end.isoformat(),
                )
                .count()
            )

            approved = (
                db.query(ContentDraft)
                .filter(
                    ContentDraft.status.in_(["approved", "published"]),
                    ContentDraft.updated_at >= week_start.isoformat(),
                    ContentDraft.updated_at < week_end.isoformat(),
                )
                .count()
            )

            rate = (approved / total * 100) if total > 0 else 0.0
            values.append(round(rate, 1))
    except ImportError:
        pass

    return values


def _weekly_decision_quality(
    db: Session, today: date, weeks_back: int
) -> list[float]:
    """Compute average decision quality score per week."""
    values = []
    try:
        from sophia.analytics.models import DecisionQualityScore

        for w in range(weeks_back, 0, -1):
            week_end = today - timedelta(weeks=w - 1)
            week_start = week_end - timedelta(days=7)

            avg = (
                db.query(func.avg(DecisionQualityScore.avg_quality_score))
                .filter(
                    DecisionQualityScore.created_at >= week_start.isoformat(),
                    DecisionQualityScore.created_at < week_end.isoformat(),
                )
                .scalar()
            )

            values.append(round(float(avg), 3) if avg else 0.0)
    except ImportError:
        pass

    return values


def _weekly_learning_counts(
    db: Session, today: date, weeks_back: int
) -> list[float]:
    """Count learnings created per week."""
    values = []
    for w in range(weeks_back, 0, -1):
        week_end = today - timedelta(weeks=w - 1)
        week_start = week_end - timedelta(days=7)

        count = (
            db.query(Learning)
            .filter(
                Learning.created_at >= week_start.isoformat(),
                Learning.created_at < week_end.isoformat(),
            )
            .count()
        )

        values.append(float(count))

    return values


# ---------------------------------------------------------------------------
# Intelligence Report Generation (LRNG-06)
# ---------------------------------------------------------------------------


def generate_intelligence_report(
    db: Session,
    client_id: Optional[int] = None,
    period_days: int = 30,
) -> IntelligenceReport:
    """Generate a periodic intelligence report with market signals.

    If client_id provided, scopes to that client. Otherwise aggregates
    across the entire portfolio.

    Covers four report sections:
    - Topic resonance: which content themes drove highest engagement
    - Competitor trends: aggregate competitor monitoring data
    - Customer questions: extracted from engagement data
    - Purchase driver signals: from high-performing content

    Args:
        db: SQLAlchemy session.
        client_id: Optional client to scope report to.
        period_days: Analysis period in days (default 30).

    Returns:
        Structured IntelligenceReport.
    """
    today = date.today()
    cutoff = today - timedelta(days=period_days)
    period_label = f"{cutoff.isoformat()} to {today.isoformat()}"

    # Topic resonance
    topic_resonance = _topic_resonance_analysis(db, client_id, cutoff)

    # Competitor trends
    competitor_trends = _competitor_trend_analysis(db, client_id, cutoff)

    # Customer questions
    customer_questions = _customer_question_analysis(db, client_id, cutoff)

    # Purchase driver signals
    purchase_drivers = _purchase_driver_analysis(db, client_id, cutoff)

    return IntelligenceReport(
        period=period_label,
        topic_resonance=topic_resonance,
        competitor_trends=competitor_trends,
        customer_questions=customer_questions,
        purchase_driver_signals=purchase_drivers,
    )


def _topic_resonance_analysis(
    db: Session, client_id: Optional[int], cutoff: date
) -> list[dict]:
    """Analyze which content themes drove highest engagement."""
    try:
        from sophia.analytics.briefing import _compute_topic_resonance

        if client_id:
            return _compute_topic_resonance(db, client_id)

        # Portfolio-wide: aggregate across all clients
        from sophia.intelligence.models import Client

        clients = db.query(Client).filter_by(is_archived=False).all()
        all_resonance: dict[str, dict] = defaultdict(
            lambda: {"total_engagement": 0, "count": 0}
        )

        for client in clients:
            client_resonance = _compute_topic_resonance(db, client.id)
            for item in client_resonance:
                pillar = item["content_pillar"]
                all_resonance[pillar]["total_engagement"] += item["total_engagement"]
                all_resonance[pillar]["count"] += item["post_count"]

        result = []
        for pillar, data in all_resonance.items():
            avg = (
                round(data["total_engagement"] / data["count"], 1)
                if data["count"] > 0
                else 0
            )
            result.append({
                "content_pillar": pillar,
                "post_count": data["count"],
                "total_engagement": data["total_engagement"],
                "avg_engagement_per_post": avg,
            })

        result.sort(key=lambda x: x["avg_engagement_per_post"], reverse=True)
        return result
    except ImportError:
        return []


def _competitor_trend_analysis(
    db: Session, client_id: Optional[int], cutoff: date
) -> list[dict]:
    """Aggregate competitor monitoring data."""
    try:
        from sophia.research.models import CompetitorSnapshot

        query = db.query(CompetitorSnapshot).filter(
            CompetitorSnapshot.created_at >= cutoff.isoformat()
        )

        if client_id:
            from sophia.research.models import Competitor

            competitor_ids = [
                c.id
                for c in db.query(Competitor)
                .filter_by(client_id=client_id)
                .all()
            ]
            if competitor_ids:
                query = query.filter(
                    CompetitorSnapshot.competitor_id.in_(competitor_ids)
                )
            else:
                return []

        snapshots = query.order_by(CompetitorSnapshot.created_at.desc()).limit(20).all()

        trends = []
        for snap in snapshots:
            themes = snap.top_content_themes if hasattr(snap, "top_content_themes") else ""
            trends.append({
                "competitor_id": snap.competitor_id,
                "themes": themes,
                "snapshot_date": (
                    snap.created_at.isoformat() if snap.created_at else ""
                ),
            })

        return trends
    except ImportError:
        return []


def _customer_question_analysis(
    db: Session, client_id: Optional[int], cutoff: date
) -> list[dict]:
    """Extract customer questions from engagement data (comments, DMs)."""
    try:
        from sophia.analytics.models import EngagementMetric

        query = db.query(EngagementMetric).filter(
            EngagementMetric.metric_name == "comments",
            EngagementMetric.metric_date >= cutoff,
        )

        if client_id:
            query = query.filter(EngagementMetric.client_id == client_id)

        # For now, surface comment volume as indicator of question activity
        comments = query.all()
        if not comments:
            return []

        return [{
            "signal": "comment_volume",
            "total_comments": sum(int(c.metric_value or 0) for c in comments),
            "period": f"last {(date.today() - cutoff).days} days",
        }]
    except ImportError:
        return []


def _purchase_driver_analysis(
    db: Session, client_id: Optional[int], cutoff: date
) -> list[dict]:
    """Identify purchase driver signals from high-performing content."""
    try:
        from sophia.analytics.models import ConversionEvent

        query = db.query(ConversionEvent).filter(
            ConversionEvent.event_date >= cutoff,
        )

        if client_id:
            query = query.filter(ConversionEvent.client_id == client_id)

        events = query.all()
        if not events:
            return []

        # Group by event type
        type_counts: dict[str, int] = defaultdict(int)
        for event in events:
            type_counts[event.event_type] += 1

        return [
            {"event_type": etype, "count": count}
            for etype, count in sorted(
                type_counts.items(), key=lambda x: x[1], reverse=True
            )
        ]
    except ImportError:
        return []
