"""Approval ORM models: PublishingQueueEntry, RecoveryLog, ApprovalEvent,
NotificationPreference, GlobalPublishState.

All models inherit from Base and TimestampMixin. No cross-client ORM
relationships -- data isolation is enforced at the service layer by
always filtering on client_id.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from sophia.db.base import Base, TimestampMixin


class PublishingQueueEntry(TimestampMixin, Base):
    """A content draft queued for publishing.

    Tracks scheduling, publish mode (auto/manual), retries, and
    platform-specific post ID/URL after successful publishing.
    """

    __tablename__ = "publishing_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_draft_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("content_drafts.id"), nullable=False, index=True
    )
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False, index=True
    )
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    publish_mode: Mapped[str] = mapped_column(
        String(20), default="auto", nullable=False
    )  # "auto" or "manual"
    status: Mapped[str] = mapped_column(
        String(20), default="queued", nullable=False
    )  # "queued", "publishing", "published", "failed", "paused"
    retry_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    platform_post_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    platform_post_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )

    __table_args__ = (
        Index("ix_publishing_queue_client_status", "client_id", "status"),
    )


class RecoveryLog(TimestampMixin, Base):
    """Content recovery log entry.

    Tracks recovery requests triggered from any interface (web, Telegram, CLI)
    or from Sophia's monitoring. Links to the original draft and optionally
    to a replacement draft.
    """

    __tablename__ = "recovery_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_draft_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("content_drafts.id"), nullable=False, index=True
    )
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False, index=True
    )
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    platform_post_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    urgency: Mapped[str] = mapped_column(
        String(20), default="immediate", nullable=False
    )  # "immediate" or "review"
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # "pending", "executing", "completed", "failed", "manual_recovery_needed"
    triggered_by: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # "operator:web", "operator:telegram", "operator:cli", "sophia:monitoring"
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    replacement_draft_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("content_drafts.id"), nullable=True
    )


class ApprovalEvent(TimestampMixin, Base):
    """Audit log for every approval state transition.

    Records who did what, when, and captures details like custom_time,
    edited_copy, publish_mode, etc. in the details JSON column.
    """

    __tablename__ = "approval_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_draft_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("content_drafts.id"), nullable=False, index=True
    )
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # "approved", "rejected", "edited", "skipped", "published", "recovered"
    actor: Mapped[str] = mapped_column(String(50), nullable=False)
    old_status: Mapped[str] = mapped_column(String(20), nullable=False)
    new_status: Mapped[str] = mapped_column(String(20), nullable=False)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class NotificationPreference(TimestampMixin, Base):
    """Per-channel notification preferences.

    Controls which events trigger notifications on each channel
    (browser, telegram, email).
    """

    __tablename__ = "notification_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False
    )  # "browser", "telegram", "email"
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    events: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )  # {"new_content": true, "publish_complete": true, ...}


class GlobalPublishState(TimestampMixin, Base):
    """Global publishing pause state.

    When is_paused=True, no content is published across any client.
    Resuming requires confirmation by default.
    """

    __tablename__ = "global_publish_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    is_paused: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    paused_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    paused_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resume_requires_confirmation: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
