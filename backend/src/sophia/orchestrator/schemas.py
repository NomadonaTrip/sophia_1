"""Pydantic v2 schemas for orchestrator models.

All response schemas use from_attributes=True for ORM compatibility.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# CycleRun
# ---------------------------------------------------------------------------


class CycleRunResponse(BaseModel):
    """Response schema for a single cycle run."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    specialist_agent_id: Optional[int] = None
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    drafts_generated: int = 0
    drafts_auto_approved: int = 0
    drafts_flagged: int = 0
    research_findings_count: int = 0
    learnings_extracted: int = 0
    observation_summary: Optional[dict] = None
    judgment_summary: Optional[dict] = None
    created_at: datetime
    updated_at: datetime


class CycleRunListResponse(BaseModel):
    """Paginated list of cycle runs."""

    items: list[CycleRunResponse]
    total: int


# ---------------------------------------------------------------------------
# CycleStage
# ---------------------------------------------------------------------------


class CycleStageResponse(BaseModel):
    """Response schema for a single cycle stage."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    cycle_run_id: int
    stage_name: str
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    decision_trace: Optional[dict] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# SpecialistAgent
# ---------------------------------------------------------------------------


class SpecialistAgentCreate(BaseModel):
    """Schema for creating a new specialist agent."""

    client_id: int
    specialty: str = "general"


class SpecialistAgentResponse(BaseModel):
    """Response schema for a specialist agent."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    specialty: str
    state_json: dict
    performance_metrics: Optional[dict] = None
    is_active: bool
    last_cycle_id: Optional[int] = None
    total_cycles: int = 0
    approval_rate: float = 0.0
    false_positive_count: int = 0
    false_positive_window_start: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# ChatMessage
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    """Schema for incoming chat messages from operator."""

    message: str
    client_context_id: Optional[int] = None


class ChatMessageResponse(BaseModel):
    """Response schema for a chat message."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    client_context_id: Optional[int] = None
    intent_type: Optional[str] = None
    metadata_json: Optional[dict] = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# AutoApprovalConfig
# ---------------------------------------------------------------------------


class AutoApprovalConfigUpdate(BaseModel):
    """Schema for updating auto-approval configuration."""

    enabled: Optional[bool] = None
    min_voice_confidence: Optional[float] = None
    require_all_gates_pass: Optional[bool] = None
    max_content_risk: Optional[str] = None
    min_historical_approval_rate: Optional[float] = None
    burn_in_cycles: Optional[int] = None
    editor_override_enabled: Optional[bool] = None


class AutoApprovalConfigResponse(BaseModel):
    """Response schema for auto-approval configuration."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    enabled: bool
    min_voice_confidence: float
    require_all_gates_pass: bool
    max_content_risk: str
    min_historical_approval_rate: float
    burn_in_cycles: int
    completed_cycles: int
    editor_override_enabled: bool
    created_at: datetime
    updated_at: datetime
