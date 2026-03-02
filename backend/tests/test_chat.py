"""Tests for chat intent detection and response routing.

Covers all 6 intent types, conversation persistence, history ordering,
and fuzzy client name matching for context switching.
"""

import asyncio

import pytest

from sophia.intelligence.schemas import ClientCreate
from sophia.intelligence.service import ClientService
from sophia.orchestrator.chat import (
    detect_intent,
    get_conversation_history,
    handle_chat_message,
)
from sophia.orchestrator.models import ChatMessage


# ---------------------------------------------------------------------------
# Intent Detection Tests
# ---------------------------------------------------------------------------


class TestDetectIntent:
    """Tests for keyword-based intent detection."""

    def test_detect_client_switch(self):
        """'Switch to Shane's Bakery' -> client_switch with client name."""
        result = detect_intent("Switch to Shane's Bakery")
        assert result["type"] == "client_switch"
        assert result["params"]["client_name"] == "Shane's Bakery"
        assert result["confidence"] == 0.8

    def test_detect_client_switch_variant(self):
        """'Let's talk about Orban Forest' -> client_switch."""
        result = detect_intent("Let's talk about Orban Forest")
        assert result["type"] == "client_switch"
        assert result["params"]["client_name"] == "Orban Forest"

    def test_detect_approval(self):
        """'approve' -> approval_action."""
        result = detect_intent("approve")
        assert result["type"] == "approval_action"
        assert result["params"]["action"] == "approve"

    def test_detect_approval_with_draft_id(self):
        """'approve draft #5' -> approval_action with draft_id."""
        result = detect_intent("approve draft #5")
        assert result["type"] == "approval_action"
        assert result["params"]["action"] == "approve"
        assert result["params"]["draft_id"] == 5

    def test_detect_cycle_trigger(self):
        """'Run cycle for Shane' -> cycle_trigger."""
        result = detect_intent("Run cycle for Shane")
        assert result["type"] == "cycle_trigger"
        assert result["params"]["client_name"] == "Shane"

    def test_detect_status(self):
        """'How is Orban Forest doing?' -> status_query."""
        result = detect_intent("How is Orban Forest doing?")
        assert result["type"] == "status_query"

    def test_detect_help(self):
        """'What can you do?' -> help."""
        result = detect_intent("What can you do?")
        assert result["type"] == "help"
        assert result["confidence"] == 0.8

    def test_detect_general_fallback(self):
        """Unmatched messages fall back to 'general'."""
        result = detect_intent("I think we should focus on summer content")
        assert result["type"] == "general"
        assert result["confidence"] == 0.5
        assert result["params"] == {}


# ---------------------------------------------------------------------------
# Conversation Persistence Tests
# ---------------------------------------------------------------------------


class TestConversationPersistence:
    """Tests for chat message persistence and history retrieval."""

    def test_conversation_persistence(self, db_session):
        """handle_chat_message persists both user and sophia messages."""

        async def _run():
            chunks = []
            async for chunk in handle_chat_message(db_session, "help"):
                chunks.append(chunk)
            return chunks

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_run())
        finally:
            loop.close()

        # Verify messages persisted
        messages = db_session.query(ChatMessage).all()
        roles = [m.role for m in messages]
        assert "user" in roles
        assert "sophia" in roles

        # Verify user message content
        user_msgs = [m for m in messages if m.role == "user"]
        assert any(m.content == "help" for m in user_msgs)

        # Verify sophia response content exists
        sophia_msgs = [m for m in messages if m.role == "sophia"]
        assert len(sophia_msgs) >= 1
        assert len(sophia_msgs[0].content) > 0

    def test_conversation_history_order(self, db_session):
        """get_conversation_history returns messages in chronological order."""
        # Create 5 messages manually
        for i in range(5):
            msg = ChatMessage(
                role="user" if i % 2 == 0 else "sophia",
                content=f"Message {i}",
            )
            db_session.add(msg)
        db_session.flush()

        # Get last 3
        history = get_conversation_history(db_session, limit=3)
        assert len(history) == 3

        # Should be in chronological order (oldest first)
        assert history[0].content == "Message 2"
        assert history[1].content == "Message 3"
        assert history[2].content == "Message 4"


# ---------------------------------------------------------------------------
# Client Switch Fuzzy Match Test
# ---------------------------------------------------------------------------


class TestClientSwitchFuzzyMatch:
    """Tests for fuzzy client name matching in context switches."""

    def test_client_switch_fuzzy_match(self, db_session, sample_client):
        """Fuzzy match succeeds: 'switch to orban' matches 'Orban Forest'."""

        async def _run():
            chunks = []
            async for chunk in handle_chat_message(
                db_session, "switch to orban"
            ):
                chunks.append(chunk)
            return chunks

        loop = asyncio.new_event_loop()
        try:
            chunks = loop.run_until_complete(_run())
        finally:
            loop.close()

        # Find context chunk
        context_chunks = [c for c in chunks if c.get("type") == "context"]
        assert len(context_chunks) == 1
        assert context_chunks[0]["client_id"] == sample_client.id
        assert context_chunks[0]["client_name"] == "Orban Forest"

        # Find text chunk
        text_chunks = [c for c in chunks if c.get("type") == "text"]
        assert len(text_chunks) >= 1
        assert "Orban Forest" in text_chunks[0]["content"]
