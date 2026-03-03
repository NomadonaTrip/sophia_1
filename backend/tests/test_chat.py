"""Tests for chat conversation history and cycle trigger wiring.

Intent detection has been removed — all messages route through Claude CLI.
These tests cover conversation history ordering and cycle trigger mechanics.
"""

import asyncio
from unittest.mock import patch

import pytest

from sophia.intelligence.schemas import ClientCreate
from sophia.intelligence.service import ClientService
from sophia.orchestrator.chat import (
    get_conversation_history,
    handle_chat_message,
    _create_and_fire_cycle,
)
from sophia.orchestrator.models import ChatMessage, CycleRun


# ---------------------------------------------------------------------------
# Conversation History Tests
# ---------------------------------------------------------------------------


class TestConversationHistory:
    """Tests for conversation history retrieval."""

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

    def test_conversation_history_client_filter(self, db_session, sample_client):
        """get_conversation_history filters by client_context_id."""
        db_session.add(ChatMessage(
            role="user", content="global msg", client_context_id=None
        ))
        db_session.add(ChatMessage(
            role="user", content="client msg",
            client_context_id=sample_client.id,
        ))
        db_session.flush()

        # Filter by client
        history = get_conversation_history(
            db_session, client_context_id=sample_client.id
        )
        assert len(history) == 1
        assert history[0].content == "client msg"


# ---------------------------------------------------------------------------
# Cycle Trigger Wiring Tests
# ---------------------------------------------------------------------------


class TestCycleTrigger:
    """Tests for cycle trigger: creates CycleRun and fires background task."""

    @patch("sophia.orchestrator.chat.asyncio.ensure_future")
    def test_create_and_fire_cycle(self, mock_ensure_future, db_session, sample_client):
        """_create_and_fire_cycle creates a CycleRun and queues background task."""
        cycle_id = _create_and_fire_cycle(db_session, sample_client.id)

        assert isinstance(cycle_id, int)
        assert cycle_id > 0

        # CycleRun should exist in DB
        cycle_runs = db_session.query(CycleRun).filter(
            CycleRun.client_id == sample_client.id
        ).all()
        assert len(cycle_runs) >= 1
        assert cycle_runs[0].status == "pending"

        # Background task was queued
        mock_ensure_future.assert_called_once()
