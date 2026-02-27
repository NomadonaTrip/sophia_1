"""Pydantic schemas for content generation models.

Provides validation for input (Create) and serialization for output (Response).
Includes voice alignment result types and platform rules.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# -- Content Draft Schemas ---------------------------------------------------


class ContentDraftCreate(BaseModel):
    """Internal schema used by the content generation service to create drafts."""

    client_id: int
    platform: str
    content_type: str
    copy: str
    image_prompt: str
    image_ratio: str
    hashtags: Optional[list[str]] = None
    alt_text: Optional[str] = None
    suggested_post_time: Optional[datetime] = None
    content_pillar: Optional[str] = None
    target_persona: Optional[str] = None
    content_format: Optional[str] = None
    freshness_window: str = "this_week"
    research_source_ids: Optional[list[int]] = None
    is_evergreen: bool = False


class ContentDraftResponse(BaseModel):
    """Full content draft response with all fields visible to operator."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    cycle_id: Optional[int] = None
    platform: str
    content_type: str
    copy: str
    image_prompt: str
    image_ratio: str
    hashtags: Optional[list[str]] = None
    alt_text: Optional[str] = None
    suggested_post_time: Optional[datetime] = None
    content_pillar: Optional[str] = None
    target_persona: Optional[str] = None
    content_format: Optional[str] = None
    freshness_window: str = "this_week"
    research_source_ids: Optional[list[int]] = None
    is_evergreen: bool = False
    rank: Optional[int] = None
    rank_reasoning: Optional[str] = None
    confidence_score: Optional[float] = None
    gate_status: str = "pending"
    gate_report: Optional[dict] = None
    voice_confidence_pct: Optional[float] = None
    has_ai_label: bool = False
    status: str = "draft"
    regeneration_count: int = 0
    regeneration_guidance: Optional[list[str]] = None
    created_at: datetime
    updated_at: datetime


class ContentBatchResponse(BaseModel):
    """Response wrapping a batch of generated content drafts."""

    items: list[ContentDraftResponse]
    client_id: int
    option_count: int
    generated_at: datetime


class ContentDraftMetadata(BaseModel):
    """Rich metadata block visible to operator per draft."""

    content_pillar: Optional[str] = None
    target_persona: Optional[str] = None
    content_format: Optional[str] = None
    freshness_window: str = "this_week"
    research_source_ids: Optional[list[int]] = None


# -- Voice Alignment Schemas -------------------------------------------------


class StylometricFeatures(BaseModel):
    """Nine stylometric features extracted via spaCy + textstat."""

    avg_sentence_length: float = 0.0
    sentence_length_std: float = 0.0
    avg_word_length: float = 0.0
    vocabulary_richness: float = 0.0
    noun_ratio: float = 0.0
    verb_ratio: float = 0.0
    adj_ratio: float = 0.0
    flesch_reading_ease: float = 0.0
    avg_syllables_per_word: float = 0.0


class VoiceAlignmentResult(BaseModel):
    """Result of voice alignment scoring against a baseline."""

    alignment_score: float = Field(..., ge=0.0, le=1.0)
    deviations: list[str] = Field(default_factory=list)
    is_drifting: bool = False
    confidence_level: str = "low"  # "low", "medium", "high"


# -- Platform Rules ----------------------------------------------------------


class PlatformRules(BaseModel):
    """Platform-specific content constraints."""

    max_chars: int
    hashtag_guidance: str
    image_ratio: str
    tone_shift: str
