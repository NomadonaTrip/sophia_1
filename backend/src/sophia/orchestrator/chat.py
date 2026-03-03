"""Chat service: Claude CLI reasoning engine + conversation history.

All operator messages are routed through Claude CLI for intelligent,
context-aware responses. Claude can emit [ACTION:...] tags to trigger
client switches, approvals, cycle triggers, etc. No keyword-based intent
detection — Claude IS the reasoning engine.

All methods take a Session as first argument (dependency injection).
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator, Optional

from sqlalchemy.orm import Session

from sophia.orchestrator.models import ChatMessage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Main Chat Entry Point
# ---------------------------------------------------------------------------


async def handle_chat_message(
    db: Session,
    message: str,
    client_context_id: Optional[int] = None,
) -> AsyncGenerator[dict, None]:
    """Process a chat message through Claude CLI, stream response via SSE.

    Persists both user and Sophia messages to the database.
    Each yield is a chunk for SSE streaming.

    Args:
        db: SQLAlchemy session.
        message: The operator's message text.
        client_context_id: Currently active client ID, if any.

    Yields:
        dicts with type/content keys for SSE events.
    """
    # Persist user message
    user_msg = ChatMessage(
        role="user",
        content=message,
        client_context_id=client_context_id,
        intent_type="claude_routed",
        metadata_json={},
    )
    db.add(user_msg)
    db.commit()

    # Stream from Claude CLI
    response_parts: list[str] = []
    context_update: Optional[dict] = None

    from sophia.orchestrator.claude_cli import stream_claude_response

    async for chunk in stream_claude_response(db, message, client_context_id):
        if chunk.get("type") == "context":
            context_update = chunk
        if chunk.get("content"):
            response_parts.append(chunk["content"])
        yield chunk

    # Persist Sophia's response
    full_response = "".join(response_parts)
    sophia_msg = ChatMessage(
        role="sophia",
        content=full_response,
        client_context_id=(
            context_update["client_id"] if context_update else client_context_id
        ),
        intent_type="claude_routed",
        metadata_json={},
    )
    db.add(sophia_msg)
    db.commit()


# ---------------------------------------------------------------------------
# Cycle Trigger (used by action executor in claude_cli.py)
# ---------------------------------------------------------------------------


def _create_and_fire_cycle(db: Session, client_id: int) -> int:
    """Create a placeholder CycleRun and fire run_daily_cycle in the background.

    Returns the cycle_id so the caller can include it in the confirmation message.
    Follows the same pattern as router.py trigger_cycle endpoint.
    """
    from sophia.orchestrator.models import CycleRun

    # Create placeholder CycleRun synchronously so caller gets an ID
    cycle = CycleRun(client_id=client_id, status="pending")
    db.add(cycle)
    db.flush()
    cycle_id = cycle.id
    db.commit()

    # Fire-and-forget with fresh session
    def _session_factory():
        from sophia.db.engine import SessionLocal

        return SessionLocal()

    async def _run_cycle():
        from sophia.orchestrator.editor import run_daily_cycle

        session = _session_factory()
        try:
            placeholder = session.get(CycleRun, cycle_id)
            if placeholder:
                session.delete(placeholder)
                session.flush()
            await run_daily_cycle(session, client_id)
            session.commit()
        except Exception:
            logger.exception(
                "Background cycle failed for client %d", client_id
            )
            session.rollback()
        finally:
            session.close()

    asyncio.ensure_future(_run_cycle())

    return cycle_id


# ---------------------------------------------------------------------------
# Conversation History
# ---------------------------------------------------------------------------


def get_conversation_history(
    db: Session,
    limit: int = 50,
    client_context_id: Optional[int] = None,
) -> list[ChatMessage]:
    """Retrieve conversation history, most recent first then reversed to chronological.

    Args:
        db: SQLAlchemy session.
        limit: Max number of messages to return.
        client_context_id: Filter by client context if provided.

    Returns:
        List of ChatMessage in chronological order (oldest first).
    """
    query = db.query(ChatMessage).order_by(ChatMessage.id.desc())

    if client_context_id is not None:
        query = query.filter(ChatMessage.client_context_id == client_context_id)

    messages = query.limit(limit).all()

    # Reverse to chronological order
    return list(reversed(messages))
