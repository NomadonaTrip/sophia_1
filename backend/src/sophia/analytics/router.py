"""Analytics REST API router.

Provides endpoints for raw metrics, analytics summary, conversion events,
campaigns, and portfolio overview. DB dependency uses placeholder pattern
(wired in main.py).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from sophia.analytics.models import (
    Campaign,
    CampaignMembership,
    ConversionEvent,
    EngagementMetric,
    KPISnapshot,
)
from sophia.analytics.schemas import (
    AnalyticsSummaryResponse,
    CampaignResponse,
    ConversionEventCreate,
    DecisionTraceResponse,
    EngagementMetricResponse,
    KPISnapshotResponse,
)

analytics_router = APIRouter(prefix="/api/analytics", tags=["analytics"])


# -- DB dependency placeholder ------------------------------------------------


def _get_db():
    """Yield a SQLAlchemy session. Lazy-imports engine to avoid slow NTFS imports at startup."""
    from sophia.db.engine import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -- Endpoints ----------------------------------------------------------------
# IMPORTANT: Static routes must be defined before parameterized {client_id}
# routes to avoid FastAPI matching "portfolio" as a client_id integer.


@analytics_router.get("/portfolio/summary")
def get_portfolio_summary(
    db: Session = Depends(_get_db),
):
    """Portfolio-level overview for morning brief.

    Returns aggregated metrics across all clients. Detailed computation
    stubbed for Plan 05-02.
    """
    from sophia.intelligence.models import Client

    client_count = db.query(Client).filter_by(is_archived=False).count()

    # Count total metrics and latest collection date
    latest_metric = (
        db.query(EngagementMetric)
        .order_by(EngagementMetric.metric_date.desc())
        .first()
    )

    return {
        "client_count": client_count,
        "total_metrics": db.query(EngagementMetric).count(),
        "latest_metric_date": (
            latest_metric.metric_date.isoformat()
            if latest_metric
            else None
        ),
        "detailed_kpis": {},  # Stubbed for Plan 05-02
        "commentary": "",  # Stubbed for Plan 05-02
    }


@analytics_router.get(
    "/{client_id}/metrics",
    response_model=list[EngagementMetricResponse],
)
def get_client_metrics(
    client_id: int,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    metric_name: Optional[str] = Query(None),
    db: Session = Depends(_get_db),
):
    """Get raw engagement metrics for a client within a date range."""
    query = db.query(EngagementMetric).filter_by(client_id=client_id)

    if start_date:
        query = query.filter(EngagementMetric.metric_date >= start_date)
    if end_date:
        query = query.filter(EngagementMetric.metric_date <= end_date)
    if metric_name:
        query = query.filter(EngagementMetric.metric_name == metric_name)

    return query.order_by(EngagementMetric.metric_date.desc()).all()


@analytics_router.get(
    "/{client_id}/summary",
    response_model=AnalyticsSummaryResponse,
)
def get_client_summary(
    client_id: int,
    db: Session = Depends(_get_db),
):
    """Get analytics summary for a client.

    Computes weekly KPIs, benchmark comparison, and KPI trends.
    Returns structured AnalyticsSummaryResponse.
    """
    from sophia.analytics.kpi import (
        compare_to_benchmark,
        compute_kpi_trends,
        compute_weekly_kpis,
    )

    # Get or compute latest KPI snapshot
    latest_kpi = (
        db.query(KPISnapshot)
        .filter_by(client_id=client_id)
        .order_by(KPISnapshot.week_end.desc())
        .first()
    )

    # If no snapshot exists, compute one for the current week
    if not latest_kpi:
        today = date.today()
        latest_kpi = compute_weekly_kpis(db, client_id, today)

    kpi_response = KPISnapshotResponse.model_validate(latest_kpi)

    # Benchmark comparison
    benchmark = compare_to_benchmark(db, client_id, latest_kpi)

    # KPI trends (last 4 weeks)
    trends = compute_kpi_trends(db, client_id, weeks=4)
    trend_data = [
        {
            "week_end": t.week_end.isoformat(),
            "engagement_rate": t.engagement_rate,
            "reach_growth_pct": t.reach_growth_pct,
            "follower_growth_pct": t.follower_growth_pct,
        }
        for t in trends
    ]

    return AnalyticsSummaryResponse(
        kpis=kpi_response,
        trends=trend_data,
        anomalies=[],  # Populated by detect_client_anomalies in briefing
        commentary="",
        benchmark=benchmark,
    )


@analytics_router.post(
    "/{client_id}/conversion",
    status_code=201,
)
def log_conversion_event(
    client_id: int,
    body: ConversionEventCreate,
    db: Session = Depends(_get_db),
):
    """Log an operator-reported conversion event."""
    event = ConversionEvent(
        client_id=client_id,
        content_draft_id=body.content_draft_id,
        event_type=body.event_type,
        source=body.source,
        event_date=body.event_date or date.today(),
        details=body.details,
        revenue_amount=body.revenue_amount,
    )
    db.add(event)
    db.flush()

    return {"id": event.id, "status": "created"}


@analytics_router.get(
    "/{client_id}/campaigns",
    response_model=list[CampaignResponse],
)
def get_client_campaigns(
    client_id: int,
    db: Session = Depends(_get_db),
):
    """List campaigns for a client with member draft IDs."""
    campaigns = (
        db.query(Campaign)
        .filter_by(client_id=client_id)
        .order_by(Campaign.start_date.desc())
        .all()
    )

    results = []
    for campaign in campaigns:
        memberships = (
            db.query(CampaignMembership)
            .filter_by(campaign_id=campaign.id)
            .all()
        )
        draft_ids = [m.content_draft_id for m in memberships]
        response = CampaignResponse.model_validate(campaign)
        response.draft_ids = draft_ids
        results.append(response)

    return results


@analytics_router.get("/{client_id}/posting-times")
def get_posting_time_performance(
    client_id: int,
    platform: str = Query("instagram"),
    db: Session = Depends(_get_db),
):
    """Get average engagement rate per posting hour for heatmap display."""
    from sophia.analytics.kpi import compute_posting_time_performance

    return compute_posting_time_performance(db, client_id, platform)


@analytics_router.post("/{client_id}/campaigns/group")
def trigger_campaign_grouping(
    client_id: int,
    db: Session = Depends(_get_db),
):
    """Trigger auto-grouping of ungrouped drafts into campaigns."""
    from sophia.analytics.campaigns import auto_group_campaigns

    campaigns = auto_group_campaigns(db, client_id)
    return {
        "campaigns_created": len(campaigns),
        "campaigns": [
            {"id": c.id, "name": c.name, "slug": c.slug}
            for c in campaigns
        ],
    }


# -- Decision trace endpoints -------------------------------------------------


@analytics_router.get(
    "/{client_id}/decisions",
    response_model=list[DecisionTraceResponse],
)
def get_decision_traces(
    client_id: int,
    draft_id: Optional[int] = Query(None),
    stage: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: Session = Depends(_get_db),
):
    """List decision traces for a client with optional filters."""
    from sophia.analytics.models import DecisionTrace

    query = db.query(DecisionTrace).filter_by(client_id=client_id)

    if draft_id is not None:
        query = query.filter(DecisionTrace.content_draft_id == draft_id)
    if stage:
        query = query.filter(DecisionTrace.stage == stage)

    return (
        query.order_by(DecisionTrace.id.desc())
        .limit(limit)
        .all()
    )


@analytics_router.get("/{client_id}/decision-quality")
def get_decision_quality(
    client_id: int,
    db: Session = Depends(_get_db),
):
    """Get decision quality scores for a client."""
    from sophia.analytics.decision_trace import get_decision_quality_context

    context = get_decision_quality_context(db, client_id)
    return context or {"decision_quality": {}, "guidance": ""}


@analytics_router.post("/{client_id}/attribute-outcomes")
def trigger_outcome_attribution(
    client_id: int,
    db: Session = Depends(_get_db),
):
    """Trigger outcome attribution batch for a client."""
    from sophia.analytics.decision_trace import attribute_batch

    count = attribute_batch(db, client_id)
    return {"traces_updated": count}


@analytics_router.get("/{client_id}/decision-context")
def get_decision_context(
    client_id: int,
    db: Session = Depends(_get_db),
):
    """Get decision quality context for content generation.

    Returns structured quality feedback suitable for injection into
    generation prompts.
    """
    from sophia.analytics.decision_trace import get_decision_quality_context

    return get_decision_quality_context(db, client_id) or {}
