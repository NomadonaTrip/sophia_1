"""Capability discovery and registry ORM models.

CapabilityGap: tracks what Sophia cannot do (detected during operations).
DiscoveredCapability: raw search results from MCP Registry / GitHub.
CapabilityProposal: evaluated capability with rubric scores and recommendation.
CapabilityRegistry: installed/approved capabilities with provenance and failure tracking.
"""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from sophia.db.base import Base, TimestampMixin


class GapStatus(str, enum.Enum):
    """Lifecycle status of a capability gap."""

    open = "open"
    searching = "searching"
    proposals_ready = "proposals_ready"
    resolved = "resolved"
    wont_fix = "wont_fix"


class ProposalStatus(str, enum.Enum):
    """Review status of a capability proposal."""

    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class CapabilityStatus(str, enum.Enum):
    """Runtime status of an installed capability."""

    active = "active"
    disabled = "disabled"
    failed = "failed"


class CapabilityGap(TimestampMixin, Base):
    """A capability Sophia cannot currently perform.

    Detected during daily cycle operations (e.g., client needs Google Business
    Profile management but no MCP server is installed for it).
    """

    __tablename__ = "capability_gaps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    detected_during: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    client_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=GapStatus.open.value
    )
    resolved_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("capability_registry.id"), nullable=True
    )
    last_searched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )


class DiscoveredCapability(TimestampMixin, Base):
    """Raw search result from MCP Registry or GitHub.

    Intermediate record before evaluation -- stores everything we
    know about a potential solution.
    """

    __tablename__ = "discovered_capabilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    gap_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("capability_gaps.id"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    version: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )
    stars: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_updated: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )


class CapabilityProposal(TimestampMixin, Base):
    """Evaluated capability proposal with rubric scores.

    Created after running a discovered capability through the four-dimension
    evaluation rubric. Presented to operator for approval/rejection.
    """

    __tablename__ = "capability_proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    gap_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("capability_gaps.id"), nullable=False
    )
    discovered_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("discovered_capabilities.id"), nullable=False
    )
    relevance_score: Mapped[int] = mapped_column(Integer, nullable=False)
    quality_score: Mapped[int] = mapped_column(Integer, nullable=False)
    security_score: Mapped[int] = mapped_column(Integer, nullable=False)
    fit_score: Mapped[int] = mapped_column(Integer, nullable=False)
    composite_score: Mapped[float] = mapped_column(Float, nullable=False)
    recommendation: Mapped[str] = mapped_column(
        String(20), nullable=False
    )
    auto_rejected: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    justification_json: Mapped[str] = mapped_column(
        Text, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ProposalStatus.pending.value
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    review_notes: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )


class CapabilityRegistry(TimestampMixin, Base):
    """Installed capability with provenance and failure tracking.

    Only created after explicit operator approval. Tracks where it came
    from, what version, and runtime health via failure counting.
    """

    __tablename__ = "capability_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(
        String(200), nullable=False, unique=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    version: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )
    installed_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=CapabilityStatus.active.value
    )
    integration_notes: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    proposal_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("capability_proposals.id"), nullable=True
    )
    failure_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    auto_disable_threshold: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5
    )
