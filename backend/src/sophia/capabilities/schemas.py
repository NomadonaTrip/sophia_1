"""Pydantic v2 schemas for capability discovery and registry.

Request/response schemas for gaps, proposals, registry entries,
and approval/rejection actions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# -- Gap schemas ---------------------------------------------------------------


class GapCreate(BaseModel):
    """Request schema for logging a new capability gap."""

    description: str = Field(..., min_length=5)
    detected_during: str = Field(..., min_length=3, max_length=100)
    client_id: Optional[int] = None


class GapResponse(BaseModel):
    """Response schema for a single capability gap."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    description: str
    detected_during: str
    client_id: Optional[int] = None
    status: str
    resolved_by_id: Optional[int] = None
    last_searched_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class GapListResponse(BaseModel):
    """Paginated list of capability gaps."""

    items: list[GapResponse]
    total: int


# -- Discovered capability schemas -------------------------------------------


class DiscoveredCapabilityResponse(BaseModel):
    """Response schema for a discovered capability (search result)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    gap_id: int
    source: str
    name: str
    description: str
    url: str
    version: Optional[str] = None
    stars: Optional[int] = None
    last_updated: Optional[datetime] = None


# -- Proposal schemas ---------------------------------------------------------


class ProposalResponse(BaseModel):
    """Response schema for a capability proposal with nested discovery data."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    gap_id: int
    discovered_id: int
    relevance_score: int
    quality_score: int
    security_score: int
    fit_score: int
    composite_score: float
    recommendation: str
    auto_rejected: bool
    rejection_reason: Optional[str] = None
    justification_json: str
    status: str
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Nested discovered capability (populated by service layer)
    discovered: Optional[DiscoveredCapabilityResponse] = None


class ProposalListResponse(BaseModel):
    """Paginated list of capability proposals."""

    items: list[ProposalResponse]
    total: int
    auto_rejected_count: int


# -- Registry schemas ---------------------------------------------------------


class RegistryEntryResponse(BaseModel):
    """Response schema for an installed capability registry entry."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    source: str
    source_url: str
    version: Optional[str] = None
    installed_at: datetime
    status: str
    integration_notes: Optional[str] = None
    proposal_id: Optional[int] = None
    failure_count: int
    auto_disable_threshold: int
    created_at: datetime
    updated_at: datetime


class RegistryListResponse(BaseModel):
    """Paginated list of installed capabilities."""

    items: list[RegistryEntryResponse]
    total: int
    active_count: int
    disabled_count: int


# -- Approval/rejection schemas -----------------------------------------------


class ApprovalRequest(BaseModel):
    """Request schema for approving a capability proposal."""

    review_notes: Optional[str] = None


class RejectionRequest(BaseModel):
    """Request schema for rejecting a capability proposal.

    Operator must provide a reason for rejection.
    """

    review_notes: str = Field(..., min_length=5)
