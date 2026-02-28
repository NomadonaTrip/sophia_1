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

    Returns latest KPI snapshot with raw metrics. Trends, anomalies,
    and AI commentary are stubbed until Plan 05-02 computation.
    """
    # Get latest KPI snapshot
    latest_kpi = (
        db.query(KPISnapshot)
        .filter_by(client_id=client_id)
        .order_by(KPISnapshot.week_end.desc())
        .first()
    )

    kpi_response = None
    if latest_kpi:
        kpi_response = KPISnapshotResponse.model_validate(latest_kpi)

    return AnalyticsSummaryResponse(
        kpis=kpi_response,
        trends=[],  # Stubbed for Plan 05-02
        anomalies=[],  # Stubbed for Plan 05-02
        commentary="",  # Stubbed for Plan 05-02
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
