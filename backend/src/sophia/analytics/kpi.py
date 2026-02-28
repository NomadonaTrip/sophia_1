"""KPI computation service.

Computes weekly KPI snapshots per client from raw engagement metrics,
approval events, and content drafts. Supports benchmark comparison
and posting time performance analysis.

All functions take a SQLAlchemy session as first arg for testability
via transaction rollback.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from sophia.analytics.models import (
    ALGO_DEPENDENT,
    ALGO_INDEPENDENT,
    EngagementMetric,
    IndustryBenchmark,
    KPISnapshot,
)

logger = logging.getLogger(__name__)


def compute_weekly_kpis(
    db: Session, client_id: int, week_end: date
) -> KPISnapshot:
    """Compute one week of KPIs for a client.

    week_start = week_end - 6 days (7-day window inclusive).

    Standard engagement KPIs are computed from EngagementMetric rows.
    Internal quality KPIs are computed from ApprovalEvent and ContentDraft.
    Algorithm-dependent and -independent summaries are stored as JSON dicts.

    Args:
        db: SQLAlchemy session.
        client_id: Client to compute KPIs for.
        week_end: End date of the week (inclusive).

    Returns:
        Persisted KPISnapshot.
    """
    week_start = week_end - timedelta(days=6)

    # Query engagement metrics for this client in date range
    metrics = (
        db.query(EngagementMetric)
        .filter(
            EngagementMetric.client_id == client_id,
            EngagementMetric.metric_date >= week_start,
            EngagementMetric.metric_date <= week_end,
        )
        .all()
    )

    # Build metric aggregates: {metric_name: [values]}
    metric_agg: dict[str, list[float]] = defaultdict(list)
    for m in metrics:
        metric_agg[m.metric_name].append(m.metric_value)

    # Compute standard engagement KPIs
    total_likes = sum(metric_agg.get("likes", [0]))
    total_comments = sum(metric_agg.get("comments", [0]))
    total_shares = sum(metric_agg.get("shares", [0]))
    total_saved = sum(metric_agg.get("saved", [0]))
    total_reach = sum(metric_agg.get("reach", [0]))

    engagement_rate = None
    if total_reach > 0:
        engagement_rate = round(
            (total_likes + total_comments + total_shares + total_saved)
            / total_reach
            * 100,
            2,
        )

    save_rate = None
    if total_reach > 0:
        save_rate = round(total_saved / total_reach * 100, 2)

    share_rate = None
    if total_reach > 0:
        share_rate = round(total_shares / total_reach * 100, 2)

    # Reach growth: compare to previous week
    prev_week_start = week_start - timedelta(days=7)
    prev_week_end = week_start - timedelta(days=1)
    prev_reach_rows = (
        db.query(func.sum(EngagementMetric.metric_value))
        .filter(
            EngagementMetric.client_id == client_id,
            EngagementMetric.metric_name == "reach",
            EngagementMetric.metric_date >= prev_week_start,
            EngagementMetric.metric_date <= prev_week_end,
        )
        .scalar()
    )
    prev_reach = prev_reach_rows or 0
    reach_growth_pct = None
    if prev_reach > 0 and total_reach > 0:
        reach_growth_pct = round(
            (total_reach - prev_reach) / prev_reach * 100, 2
        )

    # Follower growth
    total_follower_growth = sum(metric_agg.get("follower_growth", [0]))
    # Previous follower count approximation: sum of previous period
    prev_follower = (
        db.query(func.sum(EngagementMetric.metric_value))
        .filter(
            EngagementMetric.client_id == client_id,
            EngagementMetric.metric_name == "follower_count",
            EngagementMetric.metric_date >= prev_week_start,
            EngagementMetric.metric_date <= prev_week_end,
        )
        .scalar()
    )
    follower_growth_pct = None
    if prev_follower and prev_follower > 0:
        follower_growth_pct = round(
            total_follower_growth / prev_follower * 100, 2
        )

    # Internal quality KPIs from ApprovalEvent
    from sophia.approval.models import ApprovalEvent

    approval_events = (
        db.query(ApprovalEvent)
        .filter(
            ApprovalEvent.client_id == client_id,
            ApprovalEvent.created_at >= week_start.isoformat(),
            ApprovalEvent.created_at <= (week_end + timedelta(days=1)).isoformat(),
        )
        .all()
    )

    total_events = len(approval_events)
    approved_count = sum(1 for e in approval_events if e.action == "approved")
    edited_count = sum(1 for e in approval_events if e.action == "edited")
    rejected_count = sum(1 for e in approval_events if e.action == "rejected")
    unique_draft_ids = set(e.content_draft_id for e in approval_events)

    approval_rate = None
    if total_events > 0:
        approval_rate = round(approved_count / total_events * 100, 2)

    edit_frequency = None
    if len(unique_draft_ids) > 0:
        edit_frequency = round(edited_count / len(unique_draft_ids), 2)

    rejection_rate = None
    if total_events > 0:
        rejection_rate = round(rejected_count / total_events * 100, 2)

    # Regeneration count from ContentDraft
    from sophia.content.models import ContentDraft

    regen_sum = (
        db.query(func.sum(ContentDraft.regeneration_count))
        .filter(
            ContentDraft.client_id == client_id,
            ContentDraft.created_at >= week_start.isoformat(),
            ContentDraft.created_at <= (week_end + timedelta(days=1)).isoformat(),
        )
        .scalar()
    )
    regeneration_count = int(regen_sum) if regen_sum else None

    # Algo-dependent and algo-independent summaries
    algo_dep: dict[str, float] = {}
    algo_indep: dict[str, float] = {}
    for name, values in metric_agg.items():
        avg_val = round(sum(values) / len(values), 2)
        if name in ALGO_DEPENDENT:
            algo_dep[name] = avg_val
        elif name in ALGO_INDEPENDENT:
            algo_indep[name] = avg_val

    snapshot = KPISnapshot(
        client_id=client_id,
        week_start=week_start,
        week_end=week_end,
        engagement_rate=engagement_rate,
        reach_growth_pct=reach_growth_pct,
        follower_growth_pct=follower_growth_pct,
        save_rate=save_rate,
        share_rate=share_rate,
        approval_rate=approval_rate,
        edit_frequency=edit_frequency,
        rejection_rate=rejection_rate,
        regeneration_count=regeneration_count,
        algo_dependent_summary=algo_dep if algo_dep else None,
        algo_independent_summary=algo_indep if algo_indep else None,
    )
    db.add(snapshot)
    db.flush()

    logger.info(
        "Computed weekly KPIs for client %d (week %s to %s): engagement_rate=%s",
        client_id,
        week_start.isoformat(),
        week_end.isoformat(),
        engagement_rate,
    )

    return snapshot


def compute_kpi_trends(
    db: Session, client_id: int, weeks: int = 4
) -> list[KPISnapshot]:
    """Return last N weeks of KPI snapshots, ordered chronologically.

    Args:
        db: SQLAlchemy session.
        client_id: Client to retrieve trends for.
        weeks: Number of weeks to retrieve.

    Returns:
        List of KPISnapshot ordered by week_end ascending.
    """
    return (
        db.query(KPISnapshot)
        .filter(KPISnapshot.client_id == client_id)
        .order_by(KPISnapshot.week_end.asc())
        .limit(weeks)
        .all()
    )


def compare_to_benchmark(
    db: Session, client_id: int, kpi: KPISnapshot
) -> dict:
    """Compare client KPIs against industry benchmarks.

    Looks up IndustryBenchmark for the client's vertical. Returns
    comparison dict of metric_name -> {client_value, benchmark_value,
    delta_pct, is_above}. Returns empty dict if no benchmarks exist.

    Args:
        db: SQLAlchemy session.
        client_id: Client whose vertical to look up.
        kpi: KPISnapshot to compare.

    Returns:
        Dict of metric comparisons, or empty dict.
    """
    from sophia.intelligence.models import Client

    client = db.query(Client).get(client_id)
    if not client or not client.industry_vertical:
        return {}

    benchmarks = (
        db.query(IndustryBenchmark)
        .filter(IndustryBenchmark.vertical == client.industry_vertical)
        .all()
    )

    if not benchmarks:
        return {}

    # Map KPI fields to comparable metric names
    kpi_values = {
        "engagement_rate": kpi.engagement_rate,
        "save_rate": kpi.save_rate,
        "share_rate": kpi.share_rate,
    }

    result = {}
    for bm in benchmarks:
        client_value = kpi_values.get(bm.metric_name)
        if client_value is not None:
            delta_pct = round(
                (client_value - bm.benchmark_value) / bm.benchmark_value * 100
                if bm.benchmark_value != 0
                else 0,
                2,
            )
            result[bm.metric_name] = {
                "client_value": client_value,
                "benchmark_value": bm.benchmark_value,
                "delta_pct": delta_pct,
                "is_above": client_value > bm.benchmark_value,
            }

    return result


def compute_posting_time_performance(
    db: Session, client_id: int, platform: str
) -> dict:
    """Compute average engagement rate per posting hour.

    Groups published ContentDrafts by hour of published_at, then
    computes average engagement rate for each hour bucket.

    Args:
        db: SQLAlchemy session.
        client_id: Client to analyze.
        platform: Platform to filter ("facebook" or "instagram").

    Returns:
        Dict of hour (0-23) -> avg_engagement_rate for heatmap display.
    """
    from sophia.content.models import ContentDraft

    drafts = (
        db.query(ContentDraft)
        .filter(
            ContentDraft.client_id == client_id,
            ContentDraft.platform == platform,
            ContentDraft.status == "published",
            ContentDraft.published_at.isnot(None),
        )
        .all()
    )

    if not drafts:
        return {}

    # Group by hour
    hour_engagement: dict[int, list[float]] = defaultdict(list)

    for draft in drafts:
        hour = draft.published_at.hour

        # Get engagement metrics for this draft
        engagement = (
            db.query(func.sum(EngagementMetric.metric_value))
            .filter(
                EngagementMetric.content_draft_id == draft.id,
                EngagementMetric.metric_name.in_(
                    ["likes", "comments", "shares", "saved"]
                ),
            )
            .scalar()
        )
        reach = (
            db.query(func.sum(EngagementMetric.metric_value))
            .filter(
                EngagementMetric.content_draft_id == draft.id,
                EngagementMetric.metric_name == "reach",
            )
            .scalar()
        )

        if reach and reach > 0 and engagement:
            rate = engagement / reach * 100
            hour_engagement[hour].append(rate)

    result = {}
    for hour, rates in sorted(hour_engagement.items()):
        result[hour] = round(sum(rates) / len(rates), 2)

    return result
