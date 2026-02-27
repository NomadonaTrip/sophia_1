"""Pydantic schemas for approval request/response validation.

Provides typed request bodies for approval actions and a unified
response schema for all approval state transitions.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ApproveRequest(BaseModel):
    """Request body for approving a content draft."""

    publish_mode: str = Field(
        default="auto", pattern="^(auto|manual)$"
    )
    custom_post_time: Optional[datetime] = None


class RejectRequest(BaseModel):
    """Request body for rejecting a content draft."""

    tags: Optional[list[str]] = None
    guidance: Optional[str] = None


class EditRequest(BaseModel):
    """Request body for editing a content draft."""

    copy: str = Field(..., min_length=1)  # noqa: shadows BaseModel.copy (intentional)
    custom_post_time: Optional[datetime] = None


class ApprovalActionResponse(BaseModel):
    """Unified response for all approval actions."""

    draft_id: int
    old_status: str
    new_status: str
    message: str


class RecoverRequest(BaseModel):
    """Request body for triggering content recovery."""

    reason: str = Field(..., min_length=1)
    urgency: str = Field(default="immediate", pattern="^(immediate|review)$")
