"""Phase 5 analytics ORM models.

All models inherit from Base + TimestampMixin.
Engagement metrics are tagged as algorithm-dependent or algorithm-independent
at storage time for accurate performance evaluation.
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from sophia.db.base import Base, TimestampMixin

# Algorithm classification constants
# Algorithm-dependent metrics: platform decides who sees your content
ALGO_DEPENDENT = {
    "views",
    "reach",
    "impressions",
    "follower_growth",
    "profile_visits",
    "story_views",
}

# Algorithm-independent metrics: user consciously acts on your content
ALGO_INDEPENDENT = {
    "likes",
    "comments",
    "shares",
    "saved",
    "link_clicks",
    "engagement_rate_on_reached",
    "save_rate",
    "share_rate",
    "comment_quality_score",
}


class EngagementMetric(TimestampMixin, Base):
    """Raw per-post engagement data from Meta APIs.

    Each metric row represents a single metric measurement for a single
    post (or page-level) on a single date. Tagged as algorithm-dependent
    or algorithm-independent at storage time.
    """

    __tablename__ = "engagement_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False, index=True
    )
    content_draft_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("content_drafts.id"), nullable=True, index=True
    )
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(50), nullable=False)
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    metric_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    is_algorithm_dependent: Mapped[bool] = mapped_column(
        Boolean, nullable=False
    )
    period: Mapped[str] = mapped_column(
        String(10), nullable=False, default="day"
    )
    platform_post_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )

    __table_args__ = (
        Index("ix_engagement_metrics_client_date", "client_id", "metric_date"),
    )


class KPISnapshot(TimestampMixin, Base):
    """Weekly computed KPI aggregation per client.

    Separates algorithm-dependent and algorithm-independent metrics
    in JSON summaries for honest performance evaluation.
    """

    __tablename__ = "kpi_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False, index=True
    )
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    week_end: Mapped[date] = mapped_column(Date, nullable=False)

    # Engagement KPIs
    engagement_rate: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    reach_growth_pct: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    follower_growth_pct: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    save_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    share_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Operator efficiency KPIs
    approval_rate: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    edit_frequency: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    rejection_rate: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    regeneration_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )

    # Flexible storage
    custom_goals: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    algo_dependent_summary: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )
    algo_independent_summary: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )

    __table_args__ = (
        Index("ix_kpi_snapshots_client_week", "client_id", "week_end"),
    )


class Campaign(TimestampMixin, Base):
    """Auto-grouped content campaigns.

    Groups related content by pillar, topic, or manual assignment.
    """

    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    content_pillar: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    topic: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )

    __table_args__ = (
        Index("ix_campaigns_client_status", "client_id", "status"),
    )


class CampaignMembership(TimestampMixin, Base):
    """M2M between Campaign and ContentDraft."""

    __tablename__ = "campaign_memberships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("campaigns.id"), nullable=False, index=True
    )
    content_draft_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("content_drafts.id"), nullable=False, index=True
    )


class ConversionEvent(TimestampMixin, Base):
    """Funnel tracking events.

    Tracks UTM clicks, saves, follows, DMs, inquiries, and conversions.
    Source distinguishes API-detected from operator-reported events.
    """

    __tablename__ = "conversion_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False, index=True
    )
    content_draft_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("content_drafts.id"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    revenue_amount: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )


class DecisionTrace(TimestampMixin, Base):
    """Structured decision logging per content cycle stage.

    Records what was decided, why, what alternatives were considered,
    and (later) whether the prediction matched reality.
    """

    __tablename__ = "decision_traces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_draft_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("content_drafts.id"), nullable=False, index=True
    )
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False, index=True
    )
    stage: Mapped[str] = mapped_column(String(30), nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    alternatives_considered: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    predicted_outcome: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )
    actual_outcome: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )

    __table_args__ = (
        Index(
            "ix_decision_traces_draft_stage",
            "content_draft_id",
            "stage",
        ),
    )


class DecisionQualityScore(TimestampMixin, Base):
    """Rolling quality scores per decision type.

    Evaluates how well Sophia's decisions correlate with actual outcomes.
    """

    __tablename__ = "decision_quality_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False, index=True
    )
    decision_type: Mapped[str] = mapped_column(String(30), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    sample_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    avg_quality_score: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    scores_detail: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )

    __table_args__ = (
        Index(
            "ix_decision_quality_client_type_period",
            "client_id",
            "decision_type",
            "period_end",
        ),
    )


class IndustryBenchmark(TimestampMixin, Base):
    """Curated vertical benchmark data.

    Reference data for comparing client performance against industry averages.
    """

    __tablename__ = "industry_benchmarks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vertical: Mapped[str] = mapped_column(String(100), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(50), nullable=False)
    benchmark_value: Mapped[float] = mapped_column(Float, nullable=False)
    data_source: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )
    data_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "vertical", "platform", "metric_name",
            name="uq_benchmark_vertical_platform_metric",
        ),
    )
