"""Content generation ORM models: ContentDraft, EvergreenEntry,
FormatPerformance, RegenerationLog.

All models inherit from Base and TimestampMixin. No cross-client ORM
relationships -- data isolation is enforced at the service layer by
always filtering on client_id.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from sophia.db.base import Base, TimestampMixin


class ContentDraft(TimestampMixin, Base):
    """Core content draft with post copy, image prompt, metadata, and gate status.

    Each draft is platform-specific (facebook/instagram) and content-type-specific
    (feed/story). Includes rich metadata for operator review: ranking, voice
    confidence, content pillar, target persona, format, freshness window, and
    research source attribution.
    """

    __tablename__ = "content_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False, index=True
    )
    cycle_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )  # FK to cycle_runs.id deferred until cycle model exists

    # Platform and type
    platform: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "facebook" or "instagram"
    content_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "feed" or "story"

    # Content
    copy: Mapped[str] = mapped_column(Text, nullable=False)
    image_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    image_ratio: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # "1:1", "4:5", "1.91:1", "9:16"
    hashtags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    alt_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    suggested_post_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Rich metadata
    content_pillar: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    target_persona: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    content_format: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # "question", "story", "how-to", "listicle", "behind-scenes", etc.
    freshness_window: Mapped[str] = mapped_column(
        String(20), default="this_week", nullable=False
    )  # "post_within_24hrs", "this_week", "evergreen"
    research_source_ids: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True
    )  # list of research finding IDs
    is_evergreen: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # Ranking
    rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rank_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Quality gate
    gate_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # "pending", "passed", "passed_with_fix", "rejected"
    gate_report: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Voice
    voice_confidence_pct: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )

    # AI labeling compliance
    has_ai_label: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # Approval metadata (set by approval service)
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_by: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # interface: "web", "telegram", "cli"
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    custom_post_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    operator_edits: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True
    )  # list of edit records
    publish_mode: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )  # "auto" or "manual"

    # Status and regeneration
    status: Mapped[str] = mapped_column(
        String(20), default="draft", nullable=False
    )  # "draft", "in_review", "approved", "rejected", "published", "skipped", "recovered"
    regeneration_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    regeneration_guidance: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True
    )  # list of guidance strings from operator

    __table_args__ = (
        Index("ix_content_drafts_client_status", "client_id", "status"),
    )


class EvergreenEntry(TimestampMixin, Base):
    """Evergreen content bank entry.

    Tracks evergreen drafts that can be recycled on thin-research days.
    Links back to the original ContentDraft.
    """

    __tablename__ = "evergreen_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False, index=True
    )
    content_draft_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("content_drafts.id"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    content_type: Mapped[str] = mapped_column(String(20), nullable=False)
    is_used: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class FormatPerformance(TimestampMixin, Base):
    """Content format performance tracking per client per platform.

    Tracks engagement metrics per content format to enable data-driven
    format selection over time (CONT-06).
    """

    __tablename__ = "format_performance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False, index=True
    )
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    content_format: Mapped[str] = mapped_column(String(50), nullable=False)
    sample_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    avg_engagement_rate: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    avg_save_rate: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    avg_ctr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_format_perf_client_platform", "client_id", "platform"),
    )


class RegenerationLog(TimestampMixin, Base):
    """Log of regeneration attempts with operator guidance.

    Tracks guidance patterns for learning: persistent memory of what
    operators ask for reduces future regeneration needs.
    """

    __tablename__ = "regeneration_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_draft_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("content_drafts.id"), nullable=False, index=True
    )
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False, index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    guidance: Mapped[str] = mapped_column(Text, nullable=False)


class CalibrationSession(TimestampMixin, Base):
    """Interactive voice calibration session: A/B comparison rounds.

    Per-client only (no cross-client mixing). Operator picks between
    two stylistic variations over 5-10 rounds to refine voice profile.
    """

    __tablename__ = "calibration_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False, index=True
    )
    total_rounds: Mapped[int] = mapped_column(
        Integer, default=10, nullable=False
    )
    rounds_completed: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default="in_progress", nullable=False
    )  # "in_progress", "completed", "cancelled"
    voice_deltas: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True
    )  # aggregated voice preference deltas


class CalibrationRound(TimestampMixin, Base):
    """A single A/B comparison round within a calibration session.

    Each round presents two versions of the same content idea with
    different stylistic interpretations. Operator picks one.
    """

    __tablename__ = "calibration_rounds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("calibration_sessions.id"), nullable=False, index=True
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    option_a: Mapped[str] = mapped_column(Text, nullable=False)
    option_b: Mapped[str] = mapped_column(Text, nullable=False)
    selected: Mapped[Optional[str]] = mapped_column(
        String(1), nullable=True
    )  # "a" or "b"
    voice_delta: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )  # what the selection reveals about voice preferences
