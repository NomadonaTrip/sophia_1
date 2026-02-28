"""Pydantic v2 response schemas for analytics data.

All schemas use from_attributes=True for ORM compatibility.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class EngagementMetricResponse(BaseModel):
    """Response schema for a single engagement metric row."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    content_draft_id: Optional[int] = None
    platform: str
    metric_name: str
    metric_value: float
    metric_date: date
    is_algorithm_dependent: bool
    period: str
    platform_post_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class KPISnapshotResponse(BaseModel):
    """Response schema for a weekly KPI snapshot."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    week_start: date
    week_end: date
    engagement_rate: Optional[float] = None
    reach_growth_pct: Optional[float] = None
    follower_growth_pct: Optional[float] = None
    save_rate: Optional[float] = None
    share_rate: Optional[float] = None
    approval_rate: Optional[float] = None
    edit_frequency: Optional[float] = None
    rejection_rate: Optional[float] = None
    regeneration_count: Optional[int] = None
    custom_goals: Optional[dict] = None
    algo_dependent_summary: Optional[dict] = None
    algo_independent_summary: Optional[dict] = None
    created_at: datetime
    updated_at: datetime


class CampaignResponse(BaseModel):
    """Response schema for a campaign with member draft IDs."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    name: str
    slug: str
    start_date: date
    end_date: Optional[date] = None
    content_pillar: Optional[str] = None
    topic: Optional[str] = None
    status: str
    draft_ids: list[int] = []
    created_at: datetime
    updated_at: datetime


class ConversionEventCreate(BaseModel):
    """Request schema for operator-reported conversion events."""

    event_type: str
    source: str = "operator_reported"
    event_date: Optional[date] = None
    details: Optional[dict] = None
    revenue_amount: Optional[float] = None
    content_draft_id: Optional[int] = None


class DecisionTraceResponse(BaseModel):
    """Response schema for a decision trace record."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    content_draft_id: int
    client_id: int
    stage: str
    decision: str
    alternatives_considered: Optional[dict] = None
    rationale: Optional[str] = None
    evidence: Optional[dict] = None
    confidence: Optional[float] = None
    predicted_outcome: Optional[dict] = None
    actual_outcome: Optional[dict] = None
    created_at: datetime
    updated_at: datetime


class AnalyticsSummaryResponse(BaseModel):
    """Composite analytics summary for a client.

    Combines KPI snapshot, trends, anomalies, and AI commentary.
    Trends and anomalies are stubbed until Plan 05-02 computation.
    """

    kpis: Optional[KPISnapshotResponse] = None
    trends: list[dict] = []
    anomalies: list[dict] = []
    commentary: str = ""
