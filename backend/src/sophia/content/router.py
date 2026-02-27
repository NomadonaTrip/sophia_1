"""Content API router: endpoints for content drafts, regeneration, calibration,
format adaptation, evergreen bank, guidance patterns, and AI labeling.

All endpoints use proper HTTP status codes: 201 for creation, 200 for retrieval,
404 for not found, 409 for invalid state (regeneration limit, calibration
already completed).

DB dependency is a placeholder -- wired during app assembly.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from sophia.content.ai_label import get_label_requirements_summary
from sophia.content.models import ContentDraft
from sophia.content.schemas import ContentDraftResponse
from sophia.content.service import (
    analyze_rejection_patterns,
    calibrate_ranking_from_choices,
    create_calibration_session,
    explain_format_adaptations,
    finalize_calibration,
    generate_calibration_round,
    get_content_drafts,
    get_evergreen_options,
    get_format_weights,
    mark_evergreen_used,
    record_calibration_choice,
    regenerate_draft,
    suggest_voice_profile_updates,
)
from sophia.exceptions import ContentGenerationError, RegenerationLimitError

content_router = APIRouter(prefix="/api/content", tags=["content"])


# -- DB dependency placeholder ------------------------------------------------


def _get_db():
    """Placeholder DB dependency.

    In production, this yields a SQLAlchemy session from the engine.
    Wired during app assembly (same pattern as research router).
    """
    raise NotImplementedError(
        "DB dependency not wired. Call content_router.dependency_overrides "
        "or wire via app assembly."
    )


# -- Request/Response schemas -------------------------------------------------


class RegenerationRequest(BaseModel):
    guidance: str = Field(..., min_length=1, max_length=2000)


class CalibrationStartRequest(BaseModel):
    total_rounds: int = Field(default=10, ge=5, le=10)


class CalibrationChoiceRequest(BaseModel):
    selected: str = Field(..., pattern="^[ab]$")


# -- Content Draft Endpoints --------------------------------------------------


@content_router.get("/drafts")
def list_drafts(
    client_id: int = Query(...),
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(_get_db),
) -> list[ContentDraftResponse]:
    """List content drafts with optional filters."""
    drafts = get_content_drafts(db, client_id, status=status, limit=limit)
    return [ContentDraftResponse.model_validate(d) for d in drafts]


@content_router.get("/drafts/{draft_id}")
def get_draft(
    draft_id: int,
    db: Session = Depends(_get_db),
) -> ContentDraftResponse:
    """Get single draft with full details."""
    draft = db.query(ContentDraft).filter(ContentDraft.id == draft_id).first()
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return ContentDraftResponse.model_validate(draft)


@content_router.get("/batch/{client_id}/latest")
def get_latest_batch(
    client_id: int,
    db: Session = Depends(_get_db),
) -> list[ContentDraftResponse]:
    """Get the latest content batch for a client (ranked)."""
    drafts = get_content_drafts(db, client_id, limit=20)
    if not drafts:
        raise HTTPException(status_code=404, detail="No drafts found for client")
    # Group by most recent cycle_id or just return latest batch
    ranked = sorted(drafts, key=lambda d: d.rank or 999)
    return [ContentDraftResponse.model_validate(d) for d in ranked]


# -- Regeneration Endpoints ---------------------------------------------------


@content_router.post("/drafts/{draft_id}/regenerate", status_code=200)
def regenerate(
    draft_id: int,
    request: RegenerationRequest,
    db: Session = Depends(_get_db),
) -> ContentDraftResponse:
    """Regenerate a draft with guidance. Returns 409 if limit reached."""
    try:
        draft = regenerate_draft(db, draft_id, request.guidance)
        db.commit()
        return ContentDraftResponse.model_validate(draft)
    except RegenerationLimitError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ContentGenerationError as e:
        if e.reason == "not_found":
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@content_router.get("/drafts/{draft_id}/regeneration-history")
def get_regeneration_history(
    draft_id: int,
    db: Session = Depends(_get_db),
) -> list[dict]:
    """Get all regeneration attempts for a draft."""
    from sophia.content.models import RegenerationLog

    logs = (
        db.query(RegenerationLog)
        .filter(RegenerationLog.content_draft_id == draft_id)
        .order_by(RegenerationLog.attempt_number)
        .all()
    )
    return [
        {
            "attempt_number": log.attempt_number,
            "guidance": log.guidance,
            "created_at": str(log.created_at),
        }
        for log in logs
    ]


# -- Voice Calibration Endpoints (CONT-09) -----------------------------------


@content_router.post("/calibration/{client_id}/start", status_code=201)
def start_calibration(
    client_id: int,
    request: CalibrationStartRequest = CalibrationStartRequest(),
    db: Session = Depends(_get_db),
) -> dict:
    """Start a new calibration session."""
    session = create_calibration_session(db, client_id, request.total_rounds)
    db.commit()
    return {
        "id": session.id,
        "client_id": session.client_id,
        "total_rounds": session.total_rounds,
        "rounds_completed": session.rounds_completed,
        "status": session.status,
    }


@content_router.get("/calibration/{session_id}")
def get_calibration_session(
    session_id: int,
    db: Session = Depends(_get_db),
) -> dict:
    """Get session status and progress."""
    from sophia.content.models import CalibrationSession

    session = (
        db.query(CalibrationSession)
        .filter(CalibrationSession.id == session_id)
        .first()
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Calibration session not found")
    return {
        "id": session.id,
        "client_id": session.client_id,
        "total_rounds": session.total_rounds,
        "rounds_completed": session.rounds_completed,
        "status": session.status,
    }


@content_router.post("/calibration/{session_id}/round", status_code=201)
def create_calibration_round(
    session_id: int,
    db: Session = Depends(_get_db),
) -> dict:
    """Generate next A/B comparison round."""
    try:
        cal_round = generate_calibration_round(db, session_id)
        db.commit()
        return {
            "id": cal_round.id,
            "session_id": cal_round.session_id,
            "round_number": cal_round.round_number,
            "option_a": cal_round.option_a,
            "option_b": cal_round.option_b,
        }
    except ContentGenerationError as e:
        if e.reason == "not_found":
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=409, detail=str(e))


@content_router.post("/calibration/{session_id}/round/{round_id}/choose")
def choose_calibration_round(
    session_id: int,
    round_id: int,
    request: CalibrationChoiceRequest,
    db: Session = Depends(_get_db),
) -> dict:
    """Record operator's choice in a calibration round."""
    try:
        cal_round = record_calibration_choice(db, round_id, request.selected)
        db.commit()
        return {
            "id": cal_round.id,
            "round_number": cal_round.round_number,
            "selected": cal_round.selected,
            "voice_delta": cal_round.voice_delta,
        }
    except ContentGenerationError as e:
        if e.reason == "not_found":
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@content_router.post("/calibration/{session_id}/finalize")
def finalize_calibration_session(
    session_id: int,
    db: Session = Depends(_get_db),
) -> dict:
    """Finalize calibration and apply voice profile updates."""
    try:
        result = finalize_calibration(db, session_id)
        db.commit()
        return result
    except ContentGenerationError as e:
        if e.reason == "not_found":
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=409, detail=str(e))


# -- Format & Adaptation Endpoints -------------------------------------------


@content_router.get("/formats/{client_id}")
def get_format_data(
    client_id: int,
    platform: str = Query("instagram"),
    db: Session = Depends(_get_db),
) -> dict:
    """Get format performance data and current weights."""
    weights = get_format_weights(db, client_id, platform)
    return {
        "client_id": client_id,
        "platform": platform,
        "weights": weights,
    }


@content_router.get("/formats/{client_id}/explanations")
def get_format_explanations(
    client_id: int,
    db: Session = Depends(_get_db),
) -> list[str]:
    """Get natural language explanations of format adaptations."""
    return explain_format_adaptations(db, client_id)


@content_router.get("/rejection-patterns/{client_id}")
def get_rejection_patterns(
    client_id: int,
    db: Session = Depends(_get_db),
) -> dict:
    """Get rejection pattern analysis."""
    return analyze_rejection_patterns(db, client_id)


# -- Evergreen Bank Endpoints ------------------------------------------------


@content_router.get("/evergreen/{client_id}")
def list_evergreen(
    client_id: int,
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(_get_db),
) -> list[dict]:
    """List unused evergreen options."""
    entries = get_evergreen_options(db, client_id, limit=limit)
    return [
        {
            "id": e.id,
            "client_id": e.client_id,
            "content_draft_id": e.content_draft_id,
            "platform": e.platform,
            "content_type": e.content_type,
            "is_used": e.is_used,
            "created_at": str(e.created_at),
        }
        for e in entries
    ]


@content_router.post("/evergreen/{evergreen_id}/use")
def use_evergreen(
    evergreen_id: int,
    db: Session = Depends(_get_db),
) -> dict:
    """Mark an evergreen option as used."""
    try:
        entry = mark_evergreen_used(db, evergreen_id)
        db.commit()
        return {
            "id": entry.id,
            "is_used": entry.is_used,
            "used_at": str(entry.used_at),
        }
    except ContentGenerationError as e:
        raise HTTPException(status_code=404, detail=str(e))


# -- Guidance & Voice Intelligence Endpoints ---------------------------------


@content_router.get("/guidance-patterns/{client_id}")
def get_guidance_patterns(
    client_id: int,
    db: Session = Depends(_get_db),
) -> dict:
    """Get detected regeneration guidance patterns with suggestions."""
    suggestions = suggest_voice_profile_updates(db, client_id)
    return {
        "client_id": client_id,
        "suggestions": suggestions,
    }


@content_router.get("/ranking-calibration/{client_id}")
def get_ranking_calibration(
    client_id: int,
    db: Session = Depends(_get_db),
) -> dict:
    """Get ranking calibration data."""
    return calibrate_ranking_from_choices(db, client_id)


# -- AI Label Endpoints ------------------------------------------------------


@content_router.get("/ai-labels/rules")
def get_ai_label_rules() -> dict:
    """Get current AI labeling rules per platform."""
    return get_label_requirements_summary()
