"""Orchestrator REST API router with chat SSE endpoint.

Provides the chat endpoint (POST /api/orchestrator/chat) for real-time
conversational interaction, and the history endpoint for loading previous
messages. Chat responses stream via SSE using sse-starlette.

Plan 04 (Wave 3) will add cycle management endpoints to this router.
"""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from sophia.orchestrator.chat import (
    get_conversation_history,
    handle_chat_message,
)
from sophia.orchestrator.schemas import ChatMessageResponse, ChatRequest

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
