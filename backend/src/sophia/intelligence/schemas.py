"""Pydantic schemas for all intelligence models.

Provides validation for input (Create/Update) and serialization for output (Response).
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ClientCreate(BaseModel):
    """Schema for creating a new client."""

    name: str = Field(..., min_length=1, max_length=200)
    industry: str = Field(..., min_length=1)


class ClientUpdate(BaseModel):
    """Schema for partial client updates. All fields optional."""

    name: Optional[str] = None
    industry: Optional[str] = None
    business_description: Optional[str] = None
    geography_area: Optional[str] = None
    geography_radius_km: Optional[int] = None
    industry_vertical: Optional[str] = None
    target_audience: Optional[dict] = None
    content_pillars: Optional[list] = None
    posting_cadence: Optional[dict] = None
    platform_accounts: Optional[list] = None
    guardrails: Optional[dict] = None
    brand_assets: Optional[dict] = None
    competitors: Optional[list] = None
    market_scope: Optional[dict] = None
    is_archived: Optional[bool] = None
    archived_at: Optional[datetime] = None
    profile_completeness_pct: Optional[int] = None
    is_mvp_ready: Optional[bool] = None
    onboarding_state: Optional[dict] = None
    last_activity_at: Optional[datetime] = None
    last_action_summary: Optional[str] = None


class ClientResponse(BaseModel):
    """Full client response with all fields."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    industry: str
    business_description: Optional[str] = None
    geography_area: Optional[str] = None
    geography_radius_km: Optional[int] = None
    industry_vertical: Optional[str] = None
    target_audience: Optional[dict] = None
    content_pillars: Optional[list] = None
    posting_cadence: Optional[dict] = None
    platform_accounts: Optional[list] = None
    guardrails: Optional[dict] = None
    brand_assets: Optional[dict] = None
    competitors: Optional[list] = None
    market_scope: Optional[dict] = None
    is_archived: bool
    archived_at: Optional[datetime] = None
    profile_completeness_pct: int
    is_mvp_ready: bool
    onboarding_state: Optional[dict] = None
    last_activity_at: Optional[datetime] = None
    last_action_summary: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ClientRosterItem(BaseModel):
    """Compact client info for roster view."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    industry: str
    profile_completeness_pct: int
    is_mvp_ready: bool
    is_archived: bool
    last_activity_at: Optional[datetime] = None


class VoiceProfileResponse(BaseModel):
    """Voice profile response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    profile_data: dict
    overall_confidence_pct: int
    sample_count: int
    last_calibrated_at: Optional[datetime] = None


class VoiceMaterialCreate(BaseModel):
    """Schema for submitting voice source material."""

    client_id: int
    source_type: Literal[
        "social_post", "website_copy", "operator_description", "reference_account"
    ]
    content: str
    source_url: Optional[str] = None
    metadata_: Optional[dict] = None


class OnboardingStateSchema(BaseModel):
    """Schema for client onboarding progress tracking."""

    phase: str
    completed_fields: list[str]
    pending_fields: list[str]
    skipped_fields: list[str]
    started_at: datetime
    last_interaction: datetime
    session_count: int
    notes: Optional[str] = None


class MarketScopeSchema(BaseModel):
    """Schema for market scope definition."""

    geography_area: str
    geography_radius_km: int
    industry_vertical: str
    competitors: list[str]


class GuardrailsSchema(BaseModel):
    """Schema for content guardrails."""

    blocklist: list[str]
    sensitive_topics: list[str]


class AuditLogResponse(BaseModel):
    """Audit log entry response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: Optional[int] = None
    action: str
    actor: str
    details: Optional[dict] = None
    created_at: datetime


# -- Intelligence Profile Schemas -------------------------------------------


class DomainScore(BaseModel):
    """Depth and freshness score for a single intelligence domain.

    Depth is rated 1-5 based on richness of understanding (not just field counts).
    Freshness is 0-1 based on how current the entries are.
    """

    domain: str  # IntelligenceDomain value
    depth: float = Field(..., ge=0, le=5)
    freshness: float = Field(..., ge=0, le=1)
    entry_count: int
    oldest_entry: Optional[datetime] = None
    newest_entry: Optional[datetime] = None


class IntelligenceProfileResponse(BaseModel):
    """Full intelligence profile summary for a client."""

    client_id: int
    domain_scores: list[DomainScore]
    overall_completeness: float = Field(..., ge=0, le=100)
    strategic_narrative: Optional[str] = None
    gaps: list[str]


class ICPPersona(BaseModel):
    """Ideal Customer Profile persona assembled from CUSTOMERS domain intelligence.

    2-3 named personas per client with demographics, pain points,
    content preferences, and platform behavior.
    """

    name: str  # e.g., "Budget-Conscious Homeowner Beth"
    demographics: str
    pain_points: list[str]
    content_preferences: list[str]
    platform_behavior: str  # e.g., "Scrolls Facebook evenings, engages with before/after photos"


class IntelligenceEntryCreate(BaseModel):
    """Schema for creating a new intelligence entry."""

    client_id: int
    domain: str  # IntelligenceDomain value
    fact: str
    source: str
    confidence: float = Field(0.5, ge=0, le=1)
    is_significant: bool = False
