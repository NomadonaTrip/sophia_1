"""Approval REST API router with SSE endpoint.

Provides endpoints for all approval actions (approve, reject, edit, skip,
recover), the approval queue, health strip, global pause/resume, and image
upload. The events_router provides a separate SSE endpoint at /api/events.

All async endpoints call sync service functions, then publish SSE events.
Error handling: InvalidTransitionError -> 409, ContentNotFoundError -> 404.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session

from sophia.approval.events import event_bus
from sophia.approval.models import GlobalPublishState, RecoveryLog
from sophia.approval.schemas import (
    ApprovalActionResponse,
    ApproveRequest,
    EditRequest,
    RecoverRequest,
    RejectRequest,
)
from sophia.approval.service import (
    approve_draft,
    edit_draft,
    get_approval_queue,
    get_health_strip_data,
    reject_draft,
    skip_draft,
    transition_draft,
)
from sophia.content.models import ContentDraft
from sophia.exceptions import ContentNotFoundError, InvalidTransitionError, SophiaError


approval_router = APIRouter(prefix="/api/approval", tags=["approval"])
events_router = APIRouter(tags=["events"])


# -- DB dependency placeholder ------------------------------------------------


def _get_db():
    """Yield a SQLAlchemy session. Lazy-imports engine to avoid slow NTFS imports at startup."""
    from sophia.db.engine import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -- Approval Action Endpoints ------------------------------------------------


@approval_router.post("/drafts/{draft_id}/approve")
async def approve_endpoint(
    draft_id: int,
    request: ApproveRequest = ApproveRequest(),
    db: Session = Depends(_get_db),
) -> ApprovalActionResponse:
    """Approve a content draft for publishing."""
    try:
        old_draft = db.query(ContentDraft).filter(ContentDraft.id == draft_id).first()
        old_status = old_draft.status if old_draft else "unknown"

        draft = approve_draft(
            db,
            draft_id,
            publish_mode=request.publish_mode,
            custom_post_time=request.custom_post_time,
            actor="operator:web",
        )
        db.commit()

        await event_bus.publish(
            "approval",
            {"draft_id": draft.id, "action": "approved", "new_status": "approved"},
        )

        return ApprovalActionResponse(
            draft_id=draft.id,
            old_status=old_status,
            new_status=draft.status,
            message="Draft approved",
        )
    except InvalidTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ContentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SophiaError as e:
        raise HTTPException(status_code=400, detail=str(e))


@approval_router.post("/drafts/{draft_id}/reject")
async def reject_endpoint(
    draft_id: int,
    request: RejectRequest = RejectRequest(),
    db: Session = Depends(_get_db),
) -> ApprovalActionResponse:
    """Reject a content draft. Draft stays in DB for learning."""
    try:
        old_draft = db.query(ContentDraft).filter(ContentDraft.id == draft_id).first()
        old_status = old_draft.status if old_draft else "unknown"

        draft = reject_draft(
            db,
            draft_id,
            tags=request.tags,
            guidance=request.guidance,
            actor="operator:web",
        )
        db.commit()

        await event_bus.publish(
            "approval",
            {"draft_id": draft.id, "action": "rejected", "new_status": "rejected"},
        )

        return ApprovalActionResponse(
            draft_id=draft.id,
            old_status=old_status,
            new_status=draft.status,
            message="Draft rejected",
        )
    except InvalidTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ContentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SophiaError as e:
        raise HTTPException(status_code=400, detail=str(e))


@approval_router.post("/drafts/{draft_id}/edit")
async def edit_endpoint(
    draft_id: int,
    request: EditRequest,
    db: Session = Depends(_get_db),
) -> ApprovalActionResponse:
    """Edit a content draft: updates copy, then approves."""
    try:
        old_draft = db.query(ContentDraft).filter(ContentDraft.id == draft_id).first()
        old_status = old_draft.status if old_draft else "unknown"

        draft = edit_draft(
            db,
            draft_id,
            new_copy=request.copy,
            custom_post_time=request.custom_post_time,
            actor="operator:web",
        )
        db.commit()

        await event_bus.publish(
            "approval",
            {"draft_id": draft.id, "action": "edited", "new_status": "approved"},
        )

        return ApprovalActionResponse(
            draft_id=draft.id,
            old_status=old_status,
            new_status=draft.status,
            message="Draft edited and approved",
        )
    except InvalidTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ContentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SophiaError as e:
        raise HTTPException(status_code=400, detail=str(e))


@approval_router.post("/drafts/{draft_id}/skip")
async def skip_endpoint(
    draft_id: int,
    db: Session = Depends(_get_db),
) -> ApprovalActionResponse:
    """Skip a content draft."""
    try:
        old_draft = db.query(ContentDraft).filter(ContentDraft.id == draft_id).first()
        old_status = old_draft.status if old_draft else "unknown"

        draft = skip_draft(db, draft_id, actor="operator:web")
        db.commit()

        await event_bus.publish(
            "approval",
            {"draft_id": draft.id, "action": "skipped", "new_status": "skipped"},
        )

        return ApprovalActionResponse(
            draft_id=draft.id,
            old_status=old_status,
            new_status=draft.status,
            message="Draft skipped",
        )
    except InvalidTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ContentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SophiaError as e:
        raise HTTPException(status_code=400, detail=str(e))


# -- Recovery Endpoint ---------------------------------------------------------


@approval_router.post("/drafts/{draft_id}/recover")
async def recover_endpoint(
    draft_id: int,
    request: RecoverRequest,
    db: Session = Depends(_get_db),
) -> dict:
    """Trigger content recovery on a published draft.

    This is the web app's entry point for the recovery protocol.
    Validates the draft is in 'published' status before transitioning.
    """
    try:
        draft = transition_draft(
            db, draft_id, "recovered", actor="operator:web",
            details={"reason": request.reason, "urgency": request.urgency},
        )

        # Create recovery log
        recovery = RecoveryLog(
            content_draft_id=draft.id,
            client_id=draft.client_id,
            platform=draft.platform,
            urgency=request.urgency,
            reason=request.reason,
            triggered_by="operator:web",
        )
        db.add(recovery)
        db.commit()

        await event_bus.publish(
            "recovery",
            {
                "draft_id": draft.id,
                "action": "recovered",
                "urgency": request.urgency,
            },
        )

        return {
            "draft_id": draft.id,
            "status": "recovered",
            "recovery_id": recovery.id,
            "urgency": request.urgency,
            "message": f"Recovery initiated: {request.reason}",
        }
    except InvalidTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ContentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SophiaError as e:
        raise HTTPException(status_code=400, detail=str(e))


# -- Queue & Health Endpoints --------------------------------------------------


@approval_router.get("/queue")
def queue_endpoint(
    client_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(_get_db),
) -> list[dict]:
    """Get the approval queue with all fields needed by the frontend ContentItem."""
    from sophia.intelligence.models import Client

    drafts = get_approval_queue(db, client_id=client_id, status=status)

    # Build client name lookup
    client_ids = {d.client_id for d in drafts}
    clients = {c.id: c.name for c in db.query(Client).filter(Client.id.in_(client_ids)).all()} if client_ids else {}

    return [
        {
            "id": d.id,
            "client_id": d.client_id,
            "client_name": clients.get(d.client_id, f"Client {d.client_id}"),
            "platform": d.platform,
            "copy": d.copy,
            "image_prompt": d.image_prompt,
            "image_url": getattr(d, "image_url", None),
            "hashtags": d.hashtags,
            "voice_alignment_pct": d.voice_confidence_pct,
            "research_source_count": len(d.research_source_ids) if d.research_source_ids else 0,
            "content_pillar": d.content_pillar,
            "scheduled_time": str(d.suggested_post_time) if d.suggested_post_time else None,
            "publish_mode": d.publish_mode,
            "status": d.status,
            "regeneration_guidance": d.regeneration_guidance[-1] if d.regeneration_guidance else None,
            "gate_report": d.gate_report,
            "suggested_time": str(d.suggested_post_time) if d.suggested_post_time else None,
        }
        for d in drafts
    ]


@approval_router.get("/health-strip")
def health_strip_endpoint(
    db: Session = Depends(_get_db),
) -> dict:
    """Get health strip data: client status counts and posts remaining."""
    return get_health_strip_data(db)


# -- Global Pause/Resume -------------------------------------------------------


@approval_router.post("/pause")
def pause_endpoint(
    db: Session = Depends(_get_db),
) -> dict:
    """Pause all publishing globally."""
    state = db.query(GlobalPublishState).first()
    if state is None:
        state = GlobalPublishState(is_paused=True, paused_at=datetime.now(timezone.utc))
        db.add(state)
    else:
        state.is_paused = True
        state.paused_at = datetime.now(timezone.utc)
    db.commit()
    return {"is_paused": True, "paused_at": str(state.paused_at)}


@approval_router.post("/resume")
def resume_endpoint(
    db: Session = Depends(_get_db),
) -> dict:
    """Resume publishing globally."""
    state = db.query(GlobalPublishState).first()
    if state is None:
        state = GlobalPublishState(is_paused=False)
        db.add(state)
    else:
        state.is_paused = False
        state.paused_at = None
    db.commit()
    return {"is_paused": False}


# -- Image Upload ---------------------------------------------------------------


@approval_router.post("/drafts/{draft_id}/upload-image")
async def upload_image_endpoint(
    draft_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(_get_db),
) -> dict:
    """Upload an image for a draft.

    Saves to data/uploads/ and stores path on the draft's image_url field.
    Image is required before publishing.
    """
    import os
    from pathlib import Path

    draft = db.query(ContentDraft).filter(ContentDraft.id == draft_id).first()
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")

    # Create uploads directory
    upload_dir = Path("data/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Save file
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{draft_id}_{timestamp}_{file.filename}"
    filepath = upload_dir / filename

    contents = await file.read()
    with open(filepath, "wb") as f:
        f.write(contents)

    # Persist image path to draft
    draft.image_url = str(filepath)
    db.commit()

    return {
        "draft_id": draft_id,
        "image_path": str(filepath),
        "image_url": str(filepath),
        "filename": filename,
        "size_bytes": len(contents),
    }


# -- SSE Endpoint (separate router, no prefix) --------------------------------


@events_router.get("/api/events")
async def event_stream():
    """SSE endpoint for real-time approval state updates.

    Returns Server-Sent Events for all approval state changes.
    Frontend clients connect to this endpoint to receive live updates.
    """
    from sse_starlette.sse import EventSourceResponse

    async def generate():
        async for event in event_bus.subscribe():
            yield {
                "event": event["type"],
                "data": json.dumps(event["data"]),
                "retry": 5000,
            }

    return EventSourceResponse(generate())
