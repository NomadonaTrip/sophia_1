"""Client, VoiceProfile, VoiceMaterial, EnrichmentLog, AuditLog ORM models.

All models inherit from Base and TimestampMixin. No cross-client ORM relationships
exist -- data isolation is enforced at the service layer by always filtering on client_id.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sophia.db.base import Base, TimestampMixin


class Client(TimestampMixin, Base):
    """Client profile with business details, voice, and onboarding state."""

    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    industry: Mapped[str] = mapped_column(String, nullable=False)
    business_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    geography_area: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    geography_radius_km: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    industry_vertical: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # JSON fields for flexible, evolving structures
    from sqlalchemy import JSON

    target_audience: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    content_pillars: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    posting_cadence: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    platform_accounts: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    guardrails: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    brand_assets: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    competitors: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    market_scope: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Status and readiness
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    profile_completeness_pct: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    is_mvp_ready: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # Onboarding and session tracking
    onboarding_state: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    last_action_summary: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Relationships (within same client scope)
    voice_profile: Mapped[Optional["VoiceProfile"]] = relationship(
        "VoiceProfile", back_populates="client", uselist=False
    )
    voice_materials: Mapped[list["VoiceMaterial"]] = relationship(
        "VoiceMaterial", back_populates="client"
    )
    enrichment_logs: Mapped[list["EnrichmentLog"]] = relationship(
        "EnrichmentLog", back_populates="client"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        "AuditLog", back_populates="client"
    )

    __table_args__ = (Index("ix_clients_is_archived", "is_archived"),)


class VoiceProfile(TimestampMixin, Base):
    """Structured voice profile with confidence scoring per dimension."""

    __tablename__ = "voice_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), unique=True, nullable=False
    )

    from sqlalchemy import JSON

    profile_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    overall_confidence_pct: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    sample_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_calibrated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )

    client: Mapped["Client"] = relationship("Client", back_populates="voice_profile")


class VoiceMaterial(TimestampMixin, Base):
    """Raw source material used for voice profile extraction."""

    __tablename__ = "voice_materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    from sqlalchemy import JSON

    metadata_: Mapped[Optional[dict]] = mapped_column(
        "metadata", JSON, nullable=True
    )

    client: Mapped["Client"] = relationship("Client", back_populates="voice_materials")


class EnrichmentLog(TimestampMixin, Base):
    """Log of progressive enrichment changes to client profiles."""

    __tablename__ = "enrichment_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False
    )
    field_name: Mapped[str] = mapped_column(String, nullable=False)
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    client: Mapped["Client"] = relationship(
        "Client", back_populates="enrichment_logs"
    )


class AuditLog(TimestampMixin, Base):
    """Append-only audit log for all state-changing operations."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String, nullable=False)
    actor: Mapped[str] = mapped_column(String, default="sophia", nullable=False)

    from sqlalchemy import JSON

    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    before_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    after_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    client: Mapped[Optional["Client"]] = relationship(
        "Client", back_populates="audit_logs"
    )

    __table_args__ = (
        Index("ix_audit_log_client_action", "client_id", "action"),
    )
