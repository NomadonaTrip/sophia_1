"""Pydantic schemas for the agent module: learnings, insights, briefings, and reports."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Learning schemas
# ---------------------------------------------------------------------------


class LearningCreate(BaseModel):
    """Input schema for creating a new learning."""

    client_id: int
    learning_type: str
    source: str
    content: str
    confidence: float = 0.8
    supersedes_id: Optional[int] = None


class LearningResponse(BaseModel):
    """Output schema for a single learning."""

    id: int
    client_id: int
    learning_type: str
    source: str
    content: str
    confidence: float
    is_superseded: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class LearningListResponse(BaseModel):
    """Paginated list of learnings."""

    items: list[LearningResponse]
    total: int


# ---------------------------------------------------------------------------
# Business insight schemas
# ---------------------------------------------------------------------------


class InsightCreate(BaseModel):
    """Input schema for extracting a business insight."""

    client_id: int
    category: str
    fact_statement: str
    source_attribution: str
    confidence: float = 0.8


class InsightResponse(BaseModel):
    """Output schema for a business insight."""

    id: int
    client_id: int
    category: str
    fact_statement: str
    source_attribution: str
    confidence: float
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Briefing schemas
# ---------------------------------------------------------------------------


class BriefingItem(BaseModel):
    """A single item in a daily standup briefing."""

    severity: str  # "critical", "warning", "info"
    category: str  # e.g., "cycle_errors", "performance", "publishing"
    message: str
    client_name: Optional[str] = None
    action_needed: bool = False


class DailyBriefingContent(BaseModel):
    """Structured content for a daily standup briefing."""

    date: str
    items: list[BriefingItem]
    portfolio_summary: dict = Field(default_factory=dict)
    pending_approval_count: int = 0


class WeeklyBriefingContent(BaseModel):
    """Structured content for a weekly strategic briefing."""

    week_start: str
    week_end: str
    cross_client_patterns: list[dict] = Field(default_factory=list)
    improvement_metrics: dict = Field(default_factory=dict)
    strategy_recommendations: list[str] = Field(default_factory=list)
    intelligence_highlights: list[dict] = Field(default_factory=list)


class BriefingResponse(BaseModel):
    """Output schema for a persisted briefing."""

    id: int
    briefing_type: str
    content: dict  # Parsed from content_json
    generated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Improvement & trend schemas
# ---------------------------------------------------------------------------


class TrendMetric(BaseModel):
    """A metric with historical values and trend direction."""

    values: list[float] = Field(default_factory=list)
    direction: str = "insufficient_data"  # "improving", "declining", "stable", "insufficient_data"


class ImprovementReport(BaseModel):
    """Self-improvement rate across three metric categories (LRNG-05)."""

    content_quality: TrendMetric = Field(default_factory=TrendMetric)
    decision_quality: TrendMetric = Field(default_factory=TrendMetric)
    intelligence_depth: TrendMetric = Field(default_factory=TrendMetric)


# ---------------------------------------------------------------------------
# Cross-client pattern schemas
# ---------------------------------------------------------------------------


class CrossClientPattern(BaseModel):
    """A pattern detected across multiple clients (anonymized)."""

    theme: str
    evidence_count: int
    client_count: int
    source_learning_id: int
    similarity_score: float


# ---------------------------------------------------------------------------
# Intelligence report schemas
# ---------------------------------------------------------------------------


class IntelligenceReport(BaseModel):
    """Periodic intelligence report with market signals (LRNG-06)."""

    period: str
    topic_resonance: list[dict] = Field(default_factory=list)
    competitor_trends: list[dict] = Field(default_factory=list)
    customer_questions: list[dict] = Field(default_factory=list)
    purchase_driver_signals: list[dict] = Field(default_factory=list)
