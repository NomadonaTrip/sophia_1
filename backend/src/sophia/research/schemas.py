"""Pydantic schemas for research findings, digest format, and competitor analysis.

Provides validation for input and serialization for output across research
orchestration, competitor monitoring, and daily digest generation.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class FindingResponse(BaseModel):
    """Response schema for a single research finding."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    finding_type: str
    topic: str
    summary: str
    content_angles: list[str] = Field(default_factory=list)
    source_url: Optional[str] = None
    source_name: Optional[str] = None
    relevance_score: float
    confidence: float
    is_time_sensitive: bool
    created_at: datetime
    expires_at: Optional[datetime] = None


class ResearchDigest(BaseModel):
    """Daily research digest assembled per client.

    Groups findings by type, surfaces time-sensitive alerts, tracks
    research freshness and MCP source health.
    """

    client_id: int
    generated_at: datetime
    findings_by_type: dict[str, list[FindingResponse]] = Field(default_factory=dict)
    time_sensitive_alerts: list[FindingResponse] = Field(default_factory=list)
    research_freshness_pct: float = Field(0.0, ge=0, le=100)
    source_health: dict[str, str] = Field(default_factory=dict)
    total_findings: int = 0


class DigestSummary(BaseModel):
    """Lightweight digest summary for Telegram scannable bullet points."""

    client_id: int
    generated_at: datetime
    total_findings: int
    time_sensitive_count: int
    freshness_pct: float


class CompetitorAnalysis(BaseModel):
    """Structured competitor analysis results."""

    competitor_id: int
    competitor_name: str
    post_frequency_7d: Optional[int] = None
    avg_engagement_rate: Optional[float] = None
    top_content_themes: list[str] = Field(default_factory=list)
    content_tone: Optional[str] = None
    detected_gaps: list[str] = Field(default_factory=list)
    detected_threats: list[str] = Field(default_factory=list)
    opportunity_type: Optional[str] = None


class ResearchCycleRequest(BaseModel):
    """Request schema for triggering a research cycle."""

    pass  # client_id comes from path parameter


class FindingsQueryParams(BaseModel):
    """Query parameters for filtering research findings."""

    finding_type: Optional[str] = None
    min_relevance: float = 0.0
    limit: int = Field(20, ge=1, le=100)
