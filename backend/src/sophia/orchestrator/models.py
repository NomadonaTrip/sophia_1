"""Orchestrator ORM models: CycleRun, CycleStage, SpecialistAgent,
ChatMessage, AutoApprovalConfig.

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
)
from sqlalchemy.orm import Mapped, mapped_column

from sophia.db.base import Base, TimestampMixin


class CycleRun(TimestampMixin, Base):
    """A single daily ReAct cycle execution for one client.

    Records the full lifecycle from pending through completion, with
    metrics on drafts generated, auto-approved, flagged, research
    findings, and learnings extracted. JSON summaries capture the
    observation and judgment phases for audit trail.
    """

    __tablename__ = "cycle_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False, index=True
    )
    specialist_agent_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("specialist_agents.id"), nullable=True
    )

    # Lifecycle
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending, running, completed, failed, partial
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Cycle metrics
    drafts_generated: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    drafts_auto_approved: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    drafts_flagged: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    research_findings_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    learnings_extracted: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    # JSON summaries for audit trail
    observation_summary: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )
    judgment_summary: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )

    __table_args__ = (
        Index("ix_cycle_runs_client_status", "client_id", "status"),
    )


class CycleStage(TimestampMixin, Base):
    """A single stage within a cycle run (observe, research, generate, etc.).

    Each stage records its own lifecycle, duration, and a structured
    decision_trace JSON for audit trail and learning.
    """

    __tablename__ = "cycle_stages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cycle_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cycle_runs.id"), nullable=False, index=True
    )

    # Stage identity
    stage_name: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # observe, research, generate, judge, approve, learn

    # Lifecycle
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending, running, completed, failed, skipped
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    duration_ms: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )

    # Decision trace for audit trail
    decision_trace: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class SpecialistAgent(TimestampMixin, Base):
    """Persistent specialist agent that accumulates context per client.

    Tracks state, performance metrics, and approval accuracy over time.
    State JSON is capped to prevent unbounded growth (max 50 entries
    per list field via compact_state).
    """

    __tablename__ = "specialist_agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False, index=True
    )

    # Specialty and state
    specialty: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # e.g., "real_estate_content", "general"
    state_json: Mapped[dict] = mapped_column(
        JSON, default=dict, nullable=False
    )
    performance_metrics: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )

    # Lifecycle
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    last_cycle_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )

    # Cumulative stats
    total_cycles: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    approval_rate: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False
    )

    # False positive tracking (auto-approved but operator-rejected)
    false_positive_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    false_positive_window_start: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )  # For 7-day sliding window


class ChatMessage(TimestampMixin, Base):
    """Conversational message between operator (user) and Sophia.

    Supports client context switching: client_context_id tracks which
    client was active when the message was sent.
    """

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "user" or "sophia"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    client_context_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=True
    )

    # Intent classification and metadata
    intent_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )
    metadata_json: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )


class AutoApprovalConfig(TimestampMixin, Base):
    """Per-client auto-approval configuration with burn-in tracking.

    Auto-approval is disabled by default and requires completing a
    burn-in period (default 15 cycles) before activation. Thresholds
    control when content can be auto-approved without operator review.
    """

    __tablename__ = "auto_approval_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False, unique=True
    )

    # Activation
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )  # Disabled by default for burn-in

    # Thresholds
    min_voice_confidence: Mapped[float] = mapped_column(
        Float, default=0.75, nullable=False
    )
    require_all_gates_pass: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    max_content_risk: Mapped[str] = mapped_column(
        String(20), default="safe", nullable=False
    )
    min_historical_approval_rate: Mapped[float] = mapped_column(
        Float, default=0.80, nullable=False
    )

    # Burn-in tracking
    burn_in_cycles: Mapped[int] = mapped_column(
        Integer, default=15, nullable=False
    )
    completed_cycles: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    # Editor override
    editor_override_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
