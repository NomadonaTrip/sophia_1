"""Orchestrator REST API router with chat and cycle management endpoints.

Provides:
- Chat endpoint (POST /api/orchestrator/chat) for real-time SSE conversation
- Chat history endpoint (GET /api/orchestrator/chat/history)
- Cycle management: trigger, list, detail, status, and exception briefing
"""

from __future__ import annotations

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from sophia.orchestrator.chat import (
    get_conversation_history,
    handle_chat_message,
)
from sophia.orchestrator.schemas import (
    ChatMessageResponse,
    ChatRequest,
    CycleRunResponse,
    CycleStageResponse,
)

orchestrator_router = APIRouter(prefix="/api/orchestrator", tags=["orchestrator"])


# -- DB dependency -----------------------------------------------------------


def _get_db():
    """Yield a SQLAlchemy session. Lazy-imports engine to avoid slow NTFS imports at startup."""
    from sophia.db.engine import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -- Chat Endpoints ----------------------------------------------------------


@orchestrator_router.post("/chat")
async def chat_endpoint(body: ChatRequest, db: Session = Depends(_get_db)):
    """Send a message to Sophia and receive a streamed SSE response.

    The response is a stream of server-sent events, each containing a JSON
    chunk with a 'type' field ('text', 'context', etc.) and relevant data.
    The stream ends with an event type 'done'.
    """

    async def event_generator():
        async for chunk in handle_chat_message(
            db, body.message, body.client_context_id
        ):
            yield {"event": "message", "data": json.dumps(chunk)}
        yield {"event": "done", "data": ""}

    return EventSourceResponse(event_generator())


@orchestrator_router.get("/chat/history")
def chat_history(
    limit: int = Query(default=50, ge=1, le=200),
    client_context_id: Optional[int] = Query(default=None),
    db: Session = Depends(_get_db),
):
    """Retrieve conversation history for the chat interface.

    Returns messages in chronological order (oldest first).
    Optionally filter by client_context_id.
    """
    messages = get_conversation_history(db, limit, client_context_id)
    return [ChatMessageResponse.model_validate(m) for m in messages]


# -- Cycle Management Endpoints -----------------------------------------------


@orchestrator_router.post("/cycle/all")
async def trigger_all_cycles(db: Session = Depends(_get_db)):
    """Manually trigger daily cycles for all active clients.

    Starts cycles asynchronously. Returns list of client IDs scheduled.
    Must be placed BEFORE /cycle/{client_id} to avoid "all" being
    interpreted as a client_id.
    """
    from sophia.orchestrator.editor import run_all_client_cycles

    # Get session factory for run_all_client_cycles
    def _session_factory():
        from sophia.db.engine import SessionLocal

        return SessionLocal()

    # Start async -- fire and forget
    asyncio.ensure_future(run_all_client_cycles(_session_factory))

    # Return the list of active client IDs that will be processed
    from sophia.intelligence.models import Client

    clients = (
        db.query(Client.id, Client.name)
        .filter(Client.is_archived.is_(False))
        .order_by(Client.id)
        .all()
    )

    return {
        "status": "started",
        "clients": [{"id": c.id, "name": c.name} for c in clients],
    }


@orchestrator_router.post("/cycle/{client_id}")
async def trigger_cycle(client_id: int, db: Session = Depends(_get_db)):
    """Manually trigger a daily cycle for a specific client.

    Returns immediately with the CycleRun in "running" status.
    The cycle executes asynchronously in the background.
    """
    from sophia.orchestrator.editor import run_daily_cycle
    from sophia.orchestrator.models import CycleRun

    # Verify client exists
    from sophia.intelligence.models import Client

    client = db.get(Client, client_id)
    if client is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"Client {client_id} not found")

    # Create cycle run synchronously so we can return it
    cycle = CycleRun(
        client_id=client_id,
        status="pending",
    )
    db.add(cycle)
    db.flush()
    cycle_id = cycle.id
    cycle_response = CycleRunResponse.model_validate(cycle)
    db.commit()

    # Start the actual cycle in background with a fresh session
    def _session_factory():
        from sophia.db.engine import SessionLocal

        return SessionLocal()

    async def _run_cycle():
        session = _session_factory()
        try:
            # Delete the placeholder and run the real cycle
            placeholder = session.get(CycleRun, cycle_id)
            if placeholder:
                session.delete(placeholder)
                session.flush()
            await run_daily_cycle(session, client_id)
            session.commit()
        except Exception:
            import logging

            logging.getLogger(__name__).exception(
                "Background cycle failed for client %d", client_id
            )
            session.rollback()
        finally:
            session.close()

    asyncio.ensure_future(_run_cycle())

    return cycle_response


@orchestrator_router.get("/cycles/{client_id}")
def list_client_cycles(
    client_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(_get_db),
):
    """List recent cycle runs for a client, ordered by most recent first."""
    from sophia.orchestrator.models import CycleRun

    cycles = (
        db.query(CycleRun)
        .filter(CycleRun.client_id == client_id)
        .order_by(CycleRun.started_at.desc().nullslast(), CycleRun.id.desc())
        .limit(limit)
        .all()
    )

    return [CycleRunResponse.model_validate(c) for c in cycles]


@orchestrator_router.get("/cycle/{cycle_id}/stages")
def get_cycle_stages(cycle_id: int, db: Session = Depends(_get_db)):
    """Get all stages for a specific cycle run, ordered by start time."""
    from sophia.orchestrator.models import CycleStage

    stages = (
        db.query(CycleStage)
        .filter(CycleStage.cycle_run_id == cycle_id)
        .order_by(CycleStage.started_at.asc().nullslast(), CycleStage.id.asc())
        .all()
    )

    return [CycleStageResponse.model_validate(s) for s in stages]


@orchestrator_router.get("/cycle/{cycle_id}")
def get_cycle_detail(cycle_id: int, db: Session = Depends(_get_db)):
    """Get a specific cycle run with inline stages."""
    from sophia.orchestrator.models import CycleRun, CycleStage

    cycle = db.get(CycleRun, cycle_id)
    if cycle is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"Cycle {cycle_id} not found")

    stages = (
        db.query(CycleStage)
        .filter(CycleStage.cycle_run_id == cycle_id)
        .order_by(CycleStage.id.asc())
        .all()
    )

    response = CycleRunResponse.model_validate(cycle)
    return {
        **response.model_dump(),
        "stages": [CycleStageResponse.model_validate(s).model_dump() for s in stages],
    }


@orchestrator_router.get("/status")
def orchestrator_status(
    request: Request,
    db: Session = Depends(_get_db),
):
    """Overview: pending cycles today, last run per client, next scheduled run.

    Queries APScheduler for job info when available.
    """
    from sophia.intelligence.models import Client
    from sophia.orchestrator.models import CycleRun

    clients = (
        db.query(Client)
        .filter(Client.is_archived.is_(False))
        .order_by(Client.id)
        .all()
    )

    client_status = []
    for client in clients:
        last_cycle = (
            db.query(CycleRun)
            .filter(CycleRun.client_id == client.id)
            .order_by(CycleRun.id.desc())
            .first()
        )

        status = {
            "client_id": client.id,
            "client_name": client.name,
            "last_cycle": None,
            "next_scheduled": None,
        }

        if last_cycle:
            status["last_cycle"] = {
                "cycle_id": last_cycle.id,
                "status": last_cycle.status,
                "started_at": (
                    last_cycle.started_at.isoformat()
                    if last_cycle.started_at
                    else None
                ),
                "completed_at": (
                    last_cycle.completed_at.isoformat()
                    if last_cycle.completed_at
                    else None
                ),
                "auto_approved": last_cycle.drafts_auto_approved,
                "flagged": last_cycle.drafts_flagged,
            }

        # Query scheduler for next run time
        scheduler = getattr(request.app.state, "scheduler", None)
        if scheduler:
            job_id = f"daily_cycle_client_{client.id}"
            job = scheduler.get_job(job_id)
            if job and job.next_run_time:
                status["next_scheduled"] = job.next_run_time.isoformat()

        client_status.append(status)

    return {
        "total_clients": len(clients),
        "clients": client_status,
    }


@orchestrator_router.get("/exception-briefing")
def get_exception_briefing(db: Session = Depends(_get_db)):
    """Get the most recent exception briefing."""
    from sophia.agent.models import Briefing

    briefing = (
        db.query(Briefing)
        .filter(Briefing.briefing_type == "exception_briefing")
        .order_by(Briefing.id.desc())
        .first()
    )

    if briefing is None:
        return {"briefing": None, "message": "No exception briefings found"}

    return {
        "briefing": json.loads(briefing.content_json),
        "generated_at": briefing.generated_at.isoformat()
        if briefing.generated_at
        else None,
    }
