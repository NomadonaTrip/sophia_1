"""Pydantic schemas for notification preferences, logs, value signals, and email data."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# -- Preference schemas -------------------------------------------------------


class PreferenceCreate(BaseModel):
    """Create notification preferences for a client."""

    client_id: int
    email_address: str = Field(..., max_length=254)
    frequency: str = Field(default="monthly", pattern="^(weekly|biweekly|monthly|disabled)$")
    engagement_threshold: Optional[float] = None
    include_metrics: bool = True
    include_comparisons: bool = True


class PreferenceUpdate(BaseModel):
    """Update notification preferences (all fields optional)."""

    frequency: Optional[str] = Field(default=None, pattern="^(weekly|biweekly|monthly|disabled)$")
    email_address: Optional[str] = Field(default=None, max_length=254)
    engagement_threshold: Optional[float] = None
    include_metrics: Optional[bool] = None
    include_comparisons: Optional[bool] = None
    is_active: Optional[bool] = None


class PreferenceResponse(BaseModel):
    """Notification preference output."""

    id: int
    client_id: int
    frequency: str
    email_address: str
    engagement_threshold: Optional[float]
    include_metrics: bool
    include_comparisons: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# -- Notification log schemas -------------------------------------------------


class NotificationLogResponse(BaseModel):
    """Single notification log entry."""

    id: int
    client_id: int
    notification_type: str
    subject: str
    resend_message_id: Optional[str]
    status: str
    sent_at: datetime
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NotificationHistoryResponse(BaseModel):
    """Notification history with summary counts."""

    items: list[NotificationLogResponse]
    total: int
    sent_count: int
    failed_count: int


# -- Value signal schemas -----------------------------------------------------


class ValueSignalResponse(BaseModel):
    """Single value signal entry."""

    id: int
    client_id: int
    signal_type: str
    headline: str
    details: str
    content_id: Optional[int]
    metric_value: Optional[float]
    metric_baseline: Optional[float]
    status: str
    approved_at: Optional[datetime]
    sent_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ValueSignalApproval(BaseModel):
    """Request body for approving a value signal."""

    review_notes: Optional[str] = None


class ValueSignalListResponse(BaseModel):
    """Value signal list with summary counts."""

    items: list[ValueSignalResponse]
    pending_count: int
    sent_count: int


# -- Email data schemas -------------------------------------------------------


class PerformanceReportData(BaseModel):
    """Data model for rendering performance report emails."""

    client_name: str
    period: str
    metrics: dict
    highlights: list[str]
    comparisons: dict  # period-over-period comparisons


class ValueSignalEmailData(BaseModel):
    """Data model for rendering value signal emails."""

    client_name: str
    headline: str
    details: str
    metric_value: Optional[float] = None
    metric_baseline: Optional[float] = None
    call_to_action: str = "Want to see more results like this? We're already working on it."
