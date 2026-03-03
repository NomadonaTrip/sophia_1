"""Tests for Claude CLI reasoning engine.

Unit tests for action tag parsing, system prompt building, and fallback.
Integration tests mock stream_claude_response to verify chat persistence.
"""

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from sophia.intelligence.schemas import ClientCreate
from sophia.intelligence.service import ClientService
from sophia.orchestrator.claude_cli import (
    _parse_action_tags,
    build_system_prompt,
    _fallback_response,
)
from sophia.orchestrator.chat import get_conversation_history, handle_chat_message
from sophia.orchestrator.models import ChatMessage


# ---------------------------------------------------------------------------
# Action Tag Parsing
# ---------------------------------------------------------------------------


class TestParseActionTags:
    """Tests for _parse_action_tags regex extraction."""

    def test_single_tag(self):
        """One tag on its own line is extracted correctly."""
        text = "Switching you over now.\n[ACTION:switch_client:Orban Forest]\nDone!"
        clean, actions = _parse_action_tags(text)
        assert len(actions) == 1
        assert actions[0]["verb"] == "switch_client"
        assert actions[0]["args"] == ["Orban Forest"]
        assert "[ACTION:" not in clean
        assert "Switching you over now." in clean
        assert "Done!" in clean

    def test_multiple_tags(self):
        """Two tags on separate lines are both parsed."""
        text = (
            "I'll approve that and switch.\n"
            "[ACTION:approve:42]\n"
            "[ACTION:switch_client:Shane's Bakery]\n"
            "All set."
        )
        clean, actions = _parse_action_tags(text)
        assert len(actions) == 2
        assert actions[0]["verb"] == "approve"
        assert actions[0]["args"] == ["42"]
        assert actions[1]["verb"] == "switch_client"
        assert actions[1]["args"] == ["Shane's Bakery"]
        assert "[ACTION:" not in clean

    def test_no_tags(self):
        """Text without action tags is returned unchanged."""
        text = "Here's my analysis of the content strategy for this week."
        clean, actions = _parse_action_tags(text)
        assert actions == []
        assert clean == text

    def test_inline_tag_ignored(self):
        """Tag embedded in the middle of a sentence is not matched."""
        text = "You could do [ACTION:approve:5] if you want."
        clean, actions = _parse_action_tags(text)
        # The regex requires ^ anchor — inline should not match
        assert actions == []
        assert clean == text

    def test_reject_with_reason(self):
        """Reject tag with reason splits args correctly."""
        text = "[ACTION:reject:7:Too promotional]"
        clean, actions = _parse_action_tags(text)
        assert len(actions) == 1
        assert actions[0]["verb"] == "reject"
        assert actions[0]["args"] == ["7", "Too promotional"]

    def test_trigger_cycle(self):
        """Trigger cycle tag parses client ID."""
        text = "Starting a cycle now.\n[ACTION:trigger_cycle:3]"
        clean, actions = _parse_action_tags(text)
        assert len(actions) == 1
        assert actions[0]["verb"] == "trigger_cycle"
        assert actions[0]["args"] == ["3"]

    def test_create_client_action_via_tags(self):
        """create_client tag parses name and industry correctly."""
        text = "Creating the client now.\n[ACTION:create_client:Test Cafe:Coffee Shop]"
        clean, actions = _parse_action_tags(text)
        assert len(actions) == 1
        assert actions[0]["verb"] == "create_client"
        assert actions[0]["args"] == ["Test Cafe", "Coffee Shop"]
        assert "[ACTION:" not in clean
        assert "Creating the client now." in clean


# ---------------------------------------------------------------------------
# System Prompt Building
# ---------------------------------------------------------------------------


class TestBuildSystemPrompt:
    """Tests for build_system_prompt context assembly."""

    def test_prompt_with_client(self, db_session, sample_client):
        """Prompt includes active client name and industry."""
        prompt = build_system_prompt(db_session, client_context_id=sample_client.id)
        assert "Sophia" in prompt
        assert "Orban Forest" in prompt
        assert "Marketing Agency" in prompt
        assert "## Actions" in prompt

    def test_prompt_without_client(self, db_session, sample_client):
        """Prompt without active client includes roster overview."""
        prompt = build_system_prompt(db_session, client_context_id=None)
        assert "Sophia" in prompt
        assert "## Actions" in prompt
        # Client roster should appear
        assert "Client Roster" in prompt
        assert "Orban Forest" in prompt

    def test_prompt_includes_actions(self, db_session):
        """Prompt always includes available action tags."""
        prompt = build_system_prompt(db_session)
        assert "[ACTION:switch_client:" in prompt
        assert "[ACTION:approve:" in prompt
        assert "[ACTION:reject:" in prompt
        assert "[ACTION:trigger_cycle:" in prompt
        assert "[ACTION:create_client:" in prompt

    def test_prompt_includes_create_client_action(self, db_session):
        """Prompt includes create_client action with name and industry args."""
        prompt = build_system_prompt(db_session)
        assert "[ACTION:create_client:CLIENT_NAME:INDUSTRY]" in prompt

    def test_prompt_includes_agentic_section(self, db_session):
        """Prompt includes the 'How You Work' agentic tool-use instructions."""
        prompt = build_system_prompt(db_session)
        assert "## How You Work" in prompt
        assert "autonomous agent" in prompt
        assert "WebSearch" in prompt
        assert "WebFetch" in prompt
        assert "chain multiple tool calls" in prompt

    def test_prompt_history_limit_20(self, db_session):
        """Conversation history is limited to 20 messages."""
        # Insert 25 messages
        for i in range(25):
            role = "user" if i % 2 == 0 else "sophia"
            db_session.add(ChatMessage(role=role, content=f"Message {i}"))
        db_session.flush()

        prompt = build_system_prompt(db_session)
        assert "Recent Conversation" in prompt
        # Should contain the most recent messages but not all 25
        # Messages 5-24 should appear (20 most recent), not 0-4
        assert "Message 24" in prompt
        assert "Message 5" in prompt
        assert "Message 4" not in prompt

    def test_prompt_includes_conversation_history(self, db_session):
        """Prompt includes recent conversation messages."""
        # Add some chat history
        db_session.add(ChatMessage(role="user", content="Hello Sophia"))
        db_session.add(ChatMessage(role="sophia", content="Hey Tayo!"))
        db_session.flush()

        prompt = build_system_prompt(db_session)
        assert "Recent Conversation" in prompt
        assert "Hello Sophia" in prompt
        assert "Hey Tayo!" in prompt


# ---------------------------------------------------------------------------
# Fallback Response
# ---------------------------------------------------------------------------


class TestFallbackResponse:
    """Tests for _fallback_response when CLI is unavailable."""

    def test_fallback_returns_guidance(self):
        """Fallback mentions tabs as alternative."""
        resp = _fallback_response("anything")
        assert "tabs" in resp.lower() or "reasoning engine" in resp.lower()
        assert len(resp) > 20


# ---------------------------------------------------------------------------
# Chat Integration (mocked CLI)
# ---------------------------------------------------------------------------


class TestChatIntegration:
    """Integration tests mocking stream_claude_response for chat persistence."""

    def test_chat_persists_both_messages(self, db_session):
        """handle_chat_message persists user + sophia messages."""

        async def mock_stream(db, message, client_context_id=None):
            yield {"type": "text", "content": "Here's my analysis."}

        async def _run():
            chunks = []
            with patch(
                "sophia.orchestrator.claude_cli.stream_claude_response",
                side_effect=mock_stream,
            ):
                async for chunk in handle_chat_message(
                    db_session, "How's content doing?"
                ):
                    chunks.append(chunk)
            return chunks

        loop = asyncio.new_event_loop()
        try:
            chunks = loop.run_until_complete(_run())
        finally:
            loop.close()

        # Verify chunks streamed
        assert len(chunks) >= 1
        assert chunks[0]["content"] == "Here's my analysis."

        # Verify messages persisted
        messages = db_session.query(ChatMessage).all()
        roles = [m.role for m in messages]
        assert "user" in roles
        assert "sophia" in roles

        user_msgs = [m for m in messages if m.role == "user"]
        assert user_msgs[0].content == "How's content doing?"
        assert user_msgs[0].intent_type == "claude_routed"

        sophia_msgs = [m for m in messages if m.role == "sophia"]
        assert sophia_msgs[0].content == "Here's my analysis."

    def test_chat_context_switch_updates_sophia_message(self, db_session, sample_client):
        """Context switch chunk updates sophia message's client_context_id."""

        async def mock_stream(db, message, client_context_id=None):
            yield {"type": "text", "content": "Switching now."}
            yield {
                "type": "context",
                "client_id": sample_client.id,
                "client_name": sample_client.name,
            }

        async def _run():
            chunks = []
            with patch(
                "sophia.orchestrator.claude_cli.stream_claude_response",
                side_effect=mock_stream,
            ):
                async for chunk in handle_chat_message(
                    db_session, "switch to Orban"
                ):
                    chunks.append(chunk)
            return chunks

        loop = asyncio.new_event_loop()
        try:
            chunks = loop.run_until_complete(_run())
        finally:
            loop.close()

        # Sophia's message should have the switched client_id
        sophia_msgs = [
            m for m in db_session.query(ChatMessage).all()
            if m.role == "sophia"
        ]
        assert len(sophia_msgs) == 1
        assert sophia_msgs[0].client_context_id == sample_client.id

    def test_chat_empty_response_persists(self, db_session):
        """Even if Claude returns nothing, messages are still persisted."""

        async def mock_stream(db, message, client_context_id=None):
            # Yield nothing — empty generator
            return
            yield  # Make it a generator

        async def _run():
            chunks = []
            with patch(
                "sophia.orchestrator.claude_cli.stream_claude_response",
                side_effect=mock_stream,
            ):
                async for chunk in handle_chat_message(
                    db_session, "test"
                ):
                    chunks.append(chunk)
            return chunks

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_run())
        finally:
            loop.close()

        messages = db_session.query(ChatMessage).all()
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[1].role == "sophia"
        assert messages[1].content == ""
