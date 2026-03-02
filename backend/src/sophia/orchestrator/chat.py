"""Chat service: intent detection, response generation, conversation history.

Handles operator messages through keyword-based intent detection and routes
to appropriate handlers (client switch, approval actions, cycle triggers,
status queries, help). Streams responses via async generators for SSE.

All methods take a Session as first argument (dependency injection).
"""

from __future__ import annotations

import json
import logging
from typing import AsyncGenerator, Optional

from sqlalchemy.orm import Session

from sophia.orchestrator.models import ChatMessage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Intent Detection
# ---------------------------------------------------------------------------

INTENT_TYPES = {
    "client_switch": ["switch to", "let's talk about", "lets talk about", "load", "open"],
    "approval_action": ["approve", "reject", "skip"],
    "cycle_trigger": ["run cycle", "start cycle", "run daily", "generate content"],
    "status_query": ["status", "how is", "what's happening", "whats happening", "show me"],
    "help": ["help", "what can you do", "commands"],
}

# Priority order: explicit commands first, then questions, then general
_INTENT_PRIORITY = [
    "client_switch",
    "approval_action",
    "cycle_trigger",
    "help",
    "status_query",
]


def detect_intent(message: str) -> dict:
    """Detect operator intent from a chat message.

    Uses keyword matching with priority hierarchy:
    explicit commands > questions > general fallback.

    Returns:
        dict with keys: type (str), params (dict), confidence (float)
    """
    lower = message.lower().strip()

    for intent_type in _INTENT_PRIORITY:
        keywords = INTENT_TYPES[intent_type]
        for keyword in keywords:
            if keyword in lower:
                params = _extract_params(intent_type, message.strip(), lower, keyword)
                return {
                    "type": intent_type,
                    "params": params,
                    "confidence": 0.8,
                }

    return {"type": "general", "params": {}, "confidence": 0.5}


def _extract_params(intent_type: str, original: str, lowered: str, matched_keyword: str) -> dict:
    """Extract parameters from message based on intent type.

    Uses lowered message for keyword index finding but extracts values
    from the original message to preserve casing.
    """
    params: dict = {}

    if intent_type == "client_switch":
        # Extract client name after the keyword (preserve original casing)
        idx = lowered.index(matched_keyword) + len(matched_keyword)
        client_name = original[idx:].strip().strip("'\".,!?")
        if client_name:
            params["client_name"] = client_name

    elif intent_type == "approval_action":
        # Extract action and optional draft ID
        if "approve" in lowered:
            params["action"] = "approve"
        elif "reject" in lowered:
            params["action"] = "reject"
        elif "skip" in lowered:
            params["action"] = "skip"
        # Look for draft ID (e.g., "approve draft 5", "approve #5")
        import re

        id_match = re.search(r"(?:draft\s*#?|#)(\d+)", lowered)
        if id_match:
            params["draft_id"] = int(id_match.group(1))

    elif intent_type == "cycle_trigger":
        # Extract client name if present (e.g., "run cycle for Shane")
        import re

        for_match = re.search(r"(?:for|on)\s+(.+?)(?:\s*$|[.!?])", original)
        if for_match:
            params["client_name"] = for_match.group(1).strip().strip("'\"")

    return params


# ---------------------------------------------------------------------------
# Chat Message Handlers
# ---------------------------------------------------------------------------


async def handle_chat_message(
    db: Session,
    message: str,
    client_context_id: Optional[int] = None,
) -> AsyncGenerator[dict, None]:
    """Process a chat message: detect intent, route to handler, stream response.

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
    intent = detect_intent(message)
    user_msg = ChatMessage(
        role="user",
        content=message,
        client_context_id=client_context_id,
        intent_type=intent["type"],
        metadata_json={"intent": intent},
    )
    db.add(user_msg)
    db.flush()

    # Route to handler based on intent
    response_parts: list[str] = []
    context_update: Optional[dict] = None

    if intent["type"] == "client_switch":
        async for chunk in _handle_client_switch(db, intent, client_context_id):
            if chunk.get("type") == "context":
                context_update = chunk
                yield chunk
            else:
                response_parts.append(chunk.get("content", ""))
                yield chunk

    elif intent["type"] == "approval_action":
        async for chunk in _handle_approval_action(db, intent, client_context_id):
            response_parts.append(chunk.get("content", ""))
            yield chunk

    elif intent["type"] == "cycle_trigger":
        async for chunk in _handle_cycle_trigger(db, intent, client_context_id):
            response_parts.append(chunk.get("content", ""))
            yield chunk

    elif intent["type"] == "status_query":
        async for chunk in _handle_status_query(db, intent, client_context_id):
            response_parts.append(chunk.get("content", ""))
            yield chunk

    elif intent["type"] == "help":
        async for chunk in _handle_help():
            response_parts.append(chunk.get("content", ""))
            yield chunk

    else:
        async for chunk in _handle_general(db, message, client_context_id):
            response_parts.append(chunk.get("content", ""))
            yield chunk

    # Persist Sophia's response
    full_response = "".join(response_parts)
    sophia_msg = ChatMessage(
        role="sophia",
        content=full_response,
        client_context_id=context_update.get("client_id") if context_update else client_context_id,
        intent_type=intent["type"],
        metadata_json={"intent": intent},
    )
    db.add(sophia_msg)
    db.commit()


# ---------------------------------------------------------------------------
# Intent Handlers
# ---------------------------------------------------------------------------


async def _handle_client_switch(
    db: Session, intent: dict, client_context_id: Optional[int]
) -> AsyncGenerator[dict, None]:
    """Handle client context switching with fuzzy name matching."""
    client_name = intent["params"].get("client_name", "")

    if not client_name:
        yield {"type": "text", "content": "Which client would you like to switch to? Please provide a name."}
        return

    # Fuzzy match against known clients
    try:
        from sophia.intelligence.service import ClientService
        from rapidfuzz import fuzz

        clients = ClientService.list_clients(db)
    except ImportError:
        yield {"type": "text", "content": "Client service is not available. Please try again later."}
        return

    best_match = None
    best_score = 0.0
    for client in clients:
        score = fuzz.WRatio(client_name.lower(), client.name.lower())
        if score > best_score:
            best_score = score
            best_match = client

    if best_match and best_score >= 60:
        # Emit context switch event
        yield {
            "type": "context",
            "client_id": best_match.id,
            "client_name": best_match.name,
        }

        # Build summary
        summary_parts = [f"Switched to {best_match.name}."]
        if best_match.industry:
            summary_parts.append(f"Industry: {best_match.industry}.")
        if best_match.content_pillars:
            pillars = best_match.content_pillars
            if isinstance(pillars, list):
                summary_parts.append(f"Content pillars: {', '.join(pillars)}.")
        if best_match.profile_completeness_pct is not None:
            summary_parts.append(
                f"Profile completeness: {best_match.profile_completeness_pct:.0f}%."
            )

        yield {"type": "text", "content": " ".join(summary_parts)}
    else:
        # No match found -- list available clients
        try:
            client_names = [c.name for c in clients[:10]]
            names_list = ", ".join(client_names)
            yield {
                "type": "text",
                "content": f"I couldn't find a client matching '{client_name}'. Available clients: {names_list}.",
            }
        except Exception:
            yield {
                "type": "text",
                "content": f"I couldn't find a client matching '{client_name}'. Please check the name and try again.",
            }


async def _handle_approval_action(
    db: Session, intent: dict, client_context_id: Optional[int]
) -> AsyncGenerator[dict, None]:
    """Handle approval actions (approve, reject, skip)."""
    action = intent["params"].get("action", "approve")
    draft_id = intent["params"].get("draft_id")

    if draft_id:
        try:
            from sophia.approval.service import approve_draft, reject_draft, skip_draft
            from sophia.content.models import ContentDraft

            draft = db.query(ContentDraft).filter(ContentDraft.id == draft_id).first()
            if not draft:
                yield {"type": "text", "content": f"Draft #{draft_id} not found."}
                return

            if action == "approve":
                approve_draft(db, draft_id)
                yield {"type": "text", "content": f"Draft #{draft_id} approved and queued for publishing."}
            elif action == "reject":
                reject_draft(db, draft_id, reason="Rejected via chat")
                yield {"type": "text", "content": f"Draft #{draft_id} rejected."}
            elif action == "skip":
                skip_draft(db, draft_id)
                yield {"type": "text", "content": f"Draft #{draft_id} skipped."}
        except ImportError:
            yield {"type": "text", "content": f"Approval service is not available. Please use the approval queue UI."}
        except Exception as e:
            yield {"type": "text", "content": f"Could not {action} draft #{draft_id}: {e}"}
    else:
        yield {
            "type": "text",
            "content": f"To {action} a specific draft, include the draft ID. For example: '{action} draft #5'. Or visit the Approval Queue tab.",
        }


async def _handle_cycle_trigger(
    db: Session, intent: dict, client_context_id: Optional[int]
) -> AsyncGenerator[dict, None]:
    """Handle cycle trigger requests."""
    client_name = intent["params"].get("client_name")

    if client_name:
        # Try to find the client
        try:
            from sophia.intelligence.service import ClientService
            from rapidfuzz import fuzz

            clients = ClientService.list_clients(db)
            best_match = None
            best_score = 0.0
            for client in clients:
                score = fuzz.WRatio(client_name.lower(), client.name.lower())
                if score > best_score:
                    best_score = score
                    best_match = client

            if best_match and best_score >= 60:
                yield {
                    "type": "text",
                    "content": f"Starting content cycle for {best_match.name}... The cycle engine will observe, research, and generate content. Check the Morning Brief for results.",
                }
            else:
                yield {"type": "text", "content": f"I couldn't find a client matching '{client_name}'. Please check the name and try again."}
        except ImportError:
            yield {"type": "text", "content": "Client service is not available. Please try again later."}
    elif client_context_id:
        try:
            from sophia.intelligence.service import ClientService

            client = ClientService.get_client(db, client_context_id)
            yield {
                "type": "text",
                "content": f"Starting content cycle for {client.name}... The cycle engine will observe, research, and generate content. Check the Morning Brief for results.",
            }
        except (ImportError, Exception):
            yield {"type": "text", "content": "Starting content cycle for the current client... Check the Morning Brief for results."}
    else:
        yield {
            "type": "text",
            "content": "Which client should I run the cycle for? Please specify a client name, or switch to a client first.",
        }


async def _handle_status_query(
    db: Session, intent: dict, client_context_id: Optional[int]
) -> AsyncGenerator[dict, None]:
    """Handle status queries about clients or the portfolio."""
    parts = []

    # Query pending approval count
    try:
        from sophia.content.models import ContentDraft

        pending_count = (
            db.query(ContentDraft)
            .filter(ContentDraft.status == "pending_review")
            .count()
        )
        parts.append(f"{pending_count} drafts awaiting approval.")
    except (ImportError, Exception):
        pass

    # Query recent cycle runs
    try:
        from sophia.orchestrator.models import CycleRun

        recent_cycles = (
            db.query(CycleRun)
            .order_by(CycleRun.created_at.desc())
            .limit(3)
            .all()
        )
        if recent_cycles:
            cycle_info = []
            for cycle in recent_cycles:
                cycle_info.append(
                    f"Cycle #{cycle.id}: {cycle.status} ({cycle.drafts_generated} drafts)"
                )
            parts.append("Recent cycles: " + "; ".join(cycle_info) + ".")
    except (ImportError, Exception):
        pass

    # Client-specific status if context is set
    if client_context_id:
        try:
            from sophia.intelligence.service import ClientService

            client = ClientService.get_client(db, client_context_id)
            parts.insert(0, f"Status for {client.name}:")
            if client.profile_completeness_pct is not None:
                parts.append(f"Profile completeness: {client.profile_completeness_pct:.0f}%.")
        except (ImportError, Exception):
            pass

    if parts:
        yield {"type": "text", "content": " ".join(parts)}
    else:
        yield {"type": "text", "content": "Everything is looking good. No pending issues to report."}


async def _handle_help() -> AsyncGenerator[dict, None]:
    """Yield list of available chat commands."""
    help_text = (
        "Here's what I can help with:\n\n"
        "-- Client switching: 'Switch to [client name]' or 'Let's talk about [client]'\n"
        "-- Approval actions: 'Approve draft #5', 'Reject draft #3', 'Skip draft #7'\n"
        "-- Content cycles: 'Run cycle for [client]' or 'Generate content'\n"
        "-- Status updates: 'How is [client] doing?', 'Show me status'\n"
        "-- General questions: Just type naturally and I'll do my best to help\n\n"
        "You can also use the tabs above for detailed views of each area."
    )
    yield {"type": "text", "content": help_text}


async def _handle_general(
    db: Session, message: str, client_context_id: Optional[int]
) -> AsyncGenerator[dict, None]:
    """Handle general messages with contextual awareness."""
    parts = []

    if client_context_id:
        try:
            from sophia.intelligence.service import ClientService

            client = ClientService.get_client(db, client_context_id)
            parts.append(f"Noted regarding {client.name}.")
        except (ImportError, Exception):
            pass

    if not parts:
        parts.append("I understood that as a general message.")

    # Add helpful suggestions
    parts.append("Try 'help' for available commands, or switch to a client for context-aware responses.")

    yield {"type": "text", "content": " ".join(parts)}


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
