"""Client communication ORM models: NotificationPreference, NotificationLog, ValueSignal.

These models power Sophia's email notification system -- the only touchpoint
clients have with the service. Clients never log in; email is how they see
their content performance and learn about wins.

All models inherit from Base and TimestampMixin. No cross-client ORM
relationships -- data isolation is enforced at the service layer by
always filtering on client_id.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from sophia.db.base import Base, TimestampMixin


class NotificationFrequency(str, Enum):
    """How often a client receives performance reports."""

    weekly = "weekly"
    biweekly = "biweekly"
    monthly = "monthly"
    disabled = "disabled"


class NotificationPreference(TimestampMixin, Base):
    """Per-client email notification settings.

    One preference set per client. No email is ever sent to a client
    without an explicit preference record existing with is_active=True.
    The operator configures these; clients never self-serve.
    """

    __tablename__ = "client_notification_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False, unique=True
    )
    frequency: Mapped[str] = mapped_column(
        String(20), nullable=False, default="monthly"
    )
    email_address: Mapped[str] = mapped_column(String(254), nullable=False)
    engagement_threshold: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    include_metrics: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    include_comparisons: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )


class NotificationLog(TimestampMixin, Base):
    """Audit trail for every email sent to clients.

    Tracks Resend message IDs for delivery status, error messages on
    failure, and links each send back to the client.
    """

    __tablename__ = "notification_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False, index=True
    )
    notification_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # "performance_report", "value_signal", "milestone"
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    resend_message_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "sent", "failed", "bounced"
    sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_notification_log_client_type", "client_id", "notification_type"),
    )


class ValueSignal(TimestampMixin, Base):
    """A detected win worth communicating to a client.

    Value signals are the proof points that justify the monthly fee.
    "Your spring prep post drove 12 enquiries" is a value signal.

    Status flow: pending -> approved -> sent  (operator-approved path)
                 pending -> dismissed          (operator-dismissed path)

    Operator approval is required before any value signal email is sent.
    """

    __tablename__ = "value_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False, index=True
    )
    signal_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # "enquiry_driver", "engagement_milestone", "audience_growth"
    headline: Mapped[str] = mapped_column(String(200), nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False)
    content_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("content_drafts.id"), nullable=True
    )
    metric_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    metric_baseline: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # "pending", "approved", "sent", "dismissed"
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )

    __table_args__ = (
        Index("ix_value_signals_client_status", "client_id", "status"),
    )
