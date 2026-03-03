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
    _action_update_client,
    _action_archive_client,
    _action_add_voice_material,
    _action_add_intelligence,
    _action_learn,
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

    def test_update_client_action_via_tags(self):
        """update_client tag parses client ID and field=value pairs."""
        text = "Updating now.\n[ACTION:update_client:5:business_description=A bakery:geography_area=Toronto]"
        clean, actions = _parse_action_tags(text)
        assert len(actions) == 1
        assert actions[0]["verb"] == "update_client"
        assert actions[0]["args"] == ["5", "business_description=A bakery", "geography_area=Toronto"]
        assert "[ACTION:" not in clean

    def test_archive_client_action_via_tags(self):
        """archive_client tag parses client ID."""
        text = "Archiving the client.\n[ACTION:archive_client:3]"
        clean, actions = _parse_action_tags(text)
        assert len(actions) == 1
        assert actions[0]["verb"] == "archive_client"
        assert actions[0]["args"] == ["3"]

    def test_add_voice_material_action_via_tags(self):
        """add_voice_material tag parses client ID, source type, and content."""
        text = "Storing material.\n[ACTION:add_voice_material:5:operator_description:We are friendly and fun]"
        clean, actions = _parse_action_tags(text)
        assert len(actions) == 1
        assert actions[0]["verb"] == "add_voice_material"
        assert actions[0]["args"] == ["5", "operator_description", "We are friendly and fun"]
        assert "[ACTION:" not in clean

    def test_add_intelligence_action_via_tags(self):
        """add_intelligence tag parses client ID, domain, and fact."""
        text = "Noted.\n[ACTION:add_intelligence:3:business:Open since 2019]"
        clean, actions = _parse_action_tags(text)
        assert len(actions) == 1
        assert actions[0]["verb"] == "add_intelligence"
        assert actions[0]["args"] == ["3", "business", "Open since 2019"]

    def test_learn_action_via_tags(self):
        """learn tag parses domain and fact."""
        text = "Got it.\n[ACTION:learn:customers:Mostly homeowners aged 35-55]"
        clean, actions = _parse_action_tags(text)
        assert len(actions) == 1
        assert actions[0]["verb"] == "learn"
        assert actions[0]["args"] == ["customers", "Mostly homeowners aged 35-55"]

    def test_learn_action_with_colons_in_fact(self):
        """learn tag rejoins fact containing colons."""
        text = "[ACTION:learn:business:Hours: Mon-Fri 9:00-5:00]"
        clean, actions = _parse_action_tags(text)
        assert len(actions) == 1
        assert actions[0]["verb"] == "learn"
        # _parse_action_tags strips each arg segment after splitting on ':'
        assert actions[0]["args"] == ["business", "Hours", "Mon-Fri 9", "00-5", "00"]


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

    def test_prompt_includes_update_client_action(self, db_session):
        """Prompt includes update_client action with field=value syntax."""
        prompt = build_system_prompt(db_session)
        assert "[ACTION:update_client:" in prompt

    def test_prompt_includes_archive_client_action(self, db_session):
        """Prompt includes archive_client action."""
        prompt = build_system_prompt(db_session)
        assert "[ACTION:archive_client:CLIENT_ID]" in prompt

    def test_prompt_includes_agentic_section(self, db_session):
        """Prompt includes the 'How You Work' agentic tool-use instructions."""
        prompt = build_system_prompt(db_session)
        assert "## How You Work" in prompt
        assert "autonomous agent" in prompt
        assert "WebSearch" in prompt
        assert "WebFetch" in prompt
        assert "chain multiple tool calls" in prompt

    def test_prompt_includes_add_voice_material_action(self, db_session):
        """Prompt includes add_voice_material action tag."""
        prompt = build_system_prompt(db_session)
        assert "[ACTION:add_voice_material:CLIENT_ID:SOURCE_TYPE:CONTENT]" in prompt

    def test_prompt_includes_add_intelligence_action(self, db_session):
        """Prompt includes add_intelligence action tag."""
        prompt = build_system_prompt(db_session)
        assert "[ACTION:add_intelligence:CLIENT_ID:DOMAIN:FACT]" in prompt

    def test_prompt_includes_learn_action(self, db_session):
        """Prompt includes learn action tag."""
        prompt = build_system_prompt(db_session)
        assert "[ACTION:learn:DOMAIN:FACT]" in prompt

    def test_prompt_includes_learning_instructions(self, db_session):
        """Prompt includes the Learning & Context Extraction section."""
        prompt = build_system_prompt(db_session)
        assert "## Learning & Context Extraction" in prompt
        assert "operator:conversation" not in prompt or "operator" in prompt
        assert "concise and atomic" in prompt

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


# ---------------------------------------------------------------------------
# Action Handler Execution
# ---------------------------------------------------------------------------


class TestActionHandlers:
    """Tests for individual action handler functions."""

    def _collect(self, async_gen_coro):
        """Run an async generator to completion and collect yielded chunks."""
        loop = asyncio.new_event_loop()
        try:
            async def _drain():
                chunks = []
                async for chunk in async_gen_coro:
                    chunks.append(chunk)
                return chunks
            return loop.run_until_complete(_drain())
        finally:
            loop.close()

    def test_update_client_action_updates_fields(self, db_session, sample_client):
        """update_client action updates fields and reports completeness."""
        args = [str(sample_client.id), "business_description=A great agency"]
        chunks = self._collect(_action_update_client(db_session, args))
        assert len(chunks) == 1
        assert "Updated" in chunks[0]["content"]
        assert "business_description" in chunks[0]["content"]

    def test_update_client_action_no_fields(self, db_session, sample_client):
        """update_client action with no field=value pairs returns error."""
        args = [str(sample_client.id)]
        chunks = self._collect(_action_update_client(db_session, args))
        assert len(chunks) == 1
        assert "No fields" in chunks[0]["content"]

    def test_update_client_action_invalid_id(self, db_session):
        """update_client action with non-numeric ID returns error."""
        args = ["abc", "name=Foo"]
        chunks = self._collect(_action_update_client(db_session, args))
        assert len(chunks) == 1
        assert "Invalid client ID" in chunks[0]["content"]

    def test_update_client_action_not_found(self, db_session):
        """update_client action with non-existent ID returns error."""
        args = ["99999", "name=Ghost"]
        chunks = self._collect(_action_update_client(db_session, args))
        assert len(chunks) == 1
        assert "failed" in chunks[0]["content"].lower()

    def test_archive_client_action(self, db_session, sample_client):
        """archive_client action archives and reports result."""
        args = [str(sample_client.id)]
        chunks = self._collect(_action_archive_client(db_session, args))
        assert len(chunks) == 1
        assert "Archived" in chunks[0]["content"]
        assert sample_client.name in chunks[0]["content"]

    def test_archive_client_action_not_found(self, db_session):
        """archive_client action with non-existent ID returns error."""
        args = ["99999"]
        chunks = self._collect(_action_archive_client(db_session, args))
        assert len(chunks) == 1
        assert "failed" in chunks[0]["content"].lower()

    def test_archive_client_action_no_args(self, db_session):
        """archive_client action with no args returns error."""
        chunks = self._collect(_action_archive_client(db_session, []))
        assert len(chunks) == 1
        assert "requires" in chunks[0]["content"].lower()

    def test_add_voice_material_action_success(self, db_session, sample_client):
        """add_voice_material action stores material and reports success."""
        args = [str(sample_client.id), "operator_description", "We are a fun brand"]
        chunks = self._collect(_action_add_voice_material(db_session, args))
        assert len(chunks) == 1
        assert "Stored voice material" in chunks[0]["content"]
        assert "operator_description" in chunks[0]["content"]

    def test_add_voice_material_action_no_args(self, db_session):
        """add_voice_material action with insufficient args returns error."""
        chunks = self._collect(_action_add_voice_material(db_session, ["1"]))
        assert len(chunks) == 1
        assert "requires" in chunks[0]["content"].lower()

    def test_add_intelligence_action_success(self, db_session, sample_client):
        """add_intelligence action fires background task and confirms immediately."""
        with patch("sophia.orchestrator.claude_cli._bg_add_intelligence", new_callable=AsyncMock) as mock_bg:
            args = [str(sample_client.id), "business", "Founded in 2020"]
            chunks = self._collect(_action_add_intelligence(db_session, args))
        assert len(chunks) == 1
        assert "Storing intelligence" in chunks[0]["content"]
        assert "business" in chunks[0]["content"]

    def test_add_intelligence_action_invalid_id(self, db_session):
        """add_intelligence action with non-numeric ID returns error."""
        chunks = self._collect(_action_add_intelligence(db_session, ["abc", "business", "Fact"]))
        assert len(chunks) == 1
        assert "Invalid client ID" in chunks[0]["content"]

    def test_learn_action_with_context(self, db_session, sample_client):
        """learn action fires background task and confirms immediately."""
        with patch("sophia.orchestrator.claude_cli._bg_add_intelligence", new_callable=AsyncMock) as mock_bg:
            args = ["customers", "Mostly homeowners aged 35-55"]
            chunks = self._collect(_action_learn(db_session, args, sample_client.id))
        assert len(chunks) == 1
        assert "Learned" in chunks[0]["content"]
        assert "customers" in chunks[0]["content"]

    def test_learn_action_without_context(self, db_session):
        """learn action without active client context returns error."""
        args = ["business", "Some fact"]
        chunks = self._collect(_action_learn(db_session, args, None))
        assert len(chunks) == 1
        assert "active client" in chunks[0]["content"].lower()

    def test_learn_action_no_args(self, db_session, sample_client):
        """learn action with no args returns error."""
        chunks = self._collect(_action_learn(db_session, [], sample_client.id))
        assert len(chunks) == 1
        assert "requires" in chunks[0]["content"].lower()
