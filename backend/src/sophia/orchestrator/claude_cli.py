"""Claude CLI reasoning engine for Sophia chat.

Routes all operator messages through `claude -p` as a subprocess. Claude
receives rich client context, conversation history, and a list of available
actions. It reasons about the response and can emit structured [ACTION:...]
tags that the backend executes.

The CLI is invoked with --output-format stream-json for NDJSON streaming.
Text deltas are forwarded as SSE chunks to the frontend in real time.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import AsyncGenerator, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Action tag parsing
# ---------------------------------------------------------------------------

_ACTION_RE = re.compile(r"^\[ACTION:([a-z_]+):([^\]]+)\]$", re.MULTILINE)


def _parse_action_tags(text: str) -> tuple[str, list[dict]]:
    """Extract [ACTION:verb:args] tags from Claude's response.

    Tags must be on their own line. Returns (clean_text, actions).
    Each action: {"verb": str, "args": list[str]}.
    """
    actions = []
    for match in _ACTION_RE.finditer(text):
        verb = match.group(1)
        raw_args = match.group(2)
        args = [a.strip() for a in raw_args.split(":")]
        actions.append({"verb": verb, "args": args})

    # Strip tag lines from visible text
    clean = _ACTION_RE.sub("", text).strip()
    # Collapse multiple blank lines left by removal
    clean = re.sub(r"\n{3,}", "\n\n", clean)
    return clean, actions


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------


def build_system_prompt(
    db: Session,
    client_context_id: Optional[int] = None,
) -> str:
    """Assemble a context-rich system prompt for Claude CLI.

    Pulls client profile, voice, learnings, approval queue, health strip,
    portfolio roster, and conversation history from the DB.
    """
    sections: list[str] = []

    # 1. Sophia persona
    sections.append(
        "You are Sophia, an AI content strategist for Orban Forest — a managed social\n"
        "media agency serving small businesses in Southern Ontario. You speak with Tayo,\n"
        "the operator who manages client accounts. Be direct, context-aware, and\n"
        "action-oriented. Use a warm but professional tone. Keep responses concise.\n"
        "Never fabricate data — if you don't have information, say so."
    )

    # 2. Agentic tool-use instructions
    sections.append(
        "## How You Work\n"
        "You are an autonomous agent with access to powerful tools. Use them "
        "proactively to complete tasks thoroughly in a single conversation turn.\n\n"
        "**Available tools:** WebSearch (research topics, trends, competitors), "
        "WebFetch (read specific web pages), Read (read local files), "
        "Bash (run system commands), Grep (search code/data), Glob (find files).\n\n"
        "**Rules:**\n"
        "- When asked to research something, actually DO the research using WebSearch "
        "and WebFetch. Search multiple queries, read the results, synthesize findings.\n"
        "- When asked a question you cannot answer from context alone, use tools to "
        "gather the information before responding.\n"
        "- Work through multi-step tasks step by step. Do not stop after one tool "
        "call — chain multiple tool calls until the task is complete.\n"
        "- Report what you accomplished and found, not what you could do.\n"
        "- Be autonomous. Do not ask for permission to use tools — just do the work.\n"
        "- If a tool call fails, try an alternative approach rather than giving up.\n"
        "- Never produce an empty response. Always explain what happened."
    )

    # 3. Available actions
    sections.append(
        "## Actions\n"
        "You can take actions by emitting these tags, each on its OWN line.\n"
        "Only emit a tag when you are actually performing the action, not when\n"
        "discussing possibilities or asking for confirmation.\n\n"
        "[ACTION:switch_client:CLIENT_NAME]\n"
        "[ACTION:approve:DRAFT_ID]\n"
        "[ACTION:reject:DRAFT_ID:REASON]\n"
        "[ACTION:skip:DRAFT_ID]\n"
        "[ACTION:trigger_cycle:CLIENT_ID]\n"
        "[ACTION:create_client:CLIENT_NAME:INDUSTRY]\n"
        "[ACTION:update_client:CLIENT_ID:FIELD=VALUE:FIELD=VALUE:...]\n"
        "[ACTION:archive_client:CLIENT_ID]\n"
        "[ACTION:add_voice_material:CLIENT_ID:SOURCE_TYPE:CONTENT]\n"
        "[ACTION:add_intelligence:CLIENT_ID:DOMAIN:FACT]\n"
        "[ACTION:learn:DOMAIN:FACT]\n\n"
        "For update_client, fields use KEY=VALUE pairs separated by colons.\n"
        "Updatable fields: business_description, geography_area, geography_radius_km,\n"
        "industry_vertical, industry, name.\n\n"
        "For add_voice_material, SOURCE_TYPE is one of: social_post, website_copy, "
        "operator_description, reference_account.\n\n"
        "For add_intelligence and learn, DOMAIN is one of: business, industry, "
        "competitors, customers, product_service, sales_process.\n\n"
        "After emitting an action tag, briefly confirm what you did in natural language."
    )

    # 3b. Learning & Context Extraction instructions
    sections.append(
        "## Learning & Context Extraction\n"
        "When the operator mentions facts about the active client in conversation, "
        "capture them as intelligence using the `learn` action. This preserves "
        "knowledge that would otherwise be lost when conversation history scrolls "
        "out of the system prompt window.\n\n"
        "Emit `[ACTION:learn:DOMAIN:FACT]` when Tayo mentions:\n"
        "- **business**: ownership, hours, history, location details, business model\n"
        "- **industry**: market trends, seasonal patterns, regulatory changes\n"
        "- **competitors**: competitor names, strategies, strengths, weaknesses\n"
        "- **customers**: demographics, preferences, pain points, buying patterns\n"
        "- **product_service**: offerings, pricing, unique selling points, quality\n"
        "- **sales_process**: lead sources, conversion, objections, follow-up methods\n\n"
        "Rules:\n"
        "- Only emit learn actions when there is an active client context\n"
        "- Keep facts concise and atomic — one fact per action\n"
        "- Never fabricate facts — only capture what the operator actually said\n"
        "- Do not repeat facts already present in the client context above\n"
        "- Emit learn actions silently alongside your natural response"
    )

    # 4. Portfolio state (health strip)
    try:
        from sophia.approval.service import get_health_strip_data

        health = get_health_strip_data(db)
        sections.append(
            f"## Portfolio\n"
            f"{health['attention']} client(s) need attention | "
            f"{health['cruising']} cruising | "
            f"{health['posts_in_review']} draft(s) in review"
        )
    except Exception:
        logger.debug("Could not load health strip for prompt")

    # 5. Client roster overview
    try:
        from sophia.intelligence.service import ClientService

        clients = ClientService.list_clients(db)
        if clients:
            roster_lines = []
            for c in clients[:10]:
                pct = f"{c.profile_completeness_pct:.0f}%" if c.profile_completeness_pct else "?"
                roster_lines.append(f"- {c.name} (id={c.id}, {c.industry or '?'}, {pct} complete)")
            sections.append("## Client Roster\n" + "\n".join(roster_lines))
    except Exception:
        logger.debug("Could not load client roster for prompt")

    # 6. Active client context (conditional)
    if client_context_id:
        _add_client_context(db, client_context_id, sections)

    # 7. Conversation history
    try:
        from sophia.orchestrator.chat import get_conversation_history

        history = get_conversation_history(db, limit=20)
        if history:
            history_lines = []
            for msg in history:
                role = "Tayo" if msg.role == "user" else "Sophia"
                # Truncate long messages in history
                content = msg.content[:300]
                if len(msg.content) > 300:
                    content += "..."
                history_lines.append(f"{role}: {content}")
            sections.append("## Recent Conversation\n" + "\n".join(history_lines))
    except Exception:
        logger.debug("Could not load conversation history for prompt")

    return "\n\n".join(sections)


def _add_client_context(
    db: Session, client_id: int, sections: list[str]
) -> None:
    """Append active client details to prompt sections."""
    try:
        from sophia.intelligence.service import ClientService

        client = ClientService.get_client(db, client_id)
    except Exception:
        return

    parts = [f"## Active Client: {client.name} (id={client.id})"]

    if client.industry:
        parts.append(f"Industry: {client.industry}")
    if client.geography_area:
        parts.append(f"Geography: {client.geography_area}")
    if client.profile_completeness_pct is not None:
        parts.append(f"Profile completeness: {client.profile_completeness_pct:.0f}%")
    if client.business_description:
        desc = client.business_description[:300]
        parts.append(f"Description: {desc}")
    if client.content_pillars:
        pillars = client.content_pillars
        if isinstance(pillars, list):
            parts.append(f"Content pillars: {', '.join(pillars)}")

    # Voice profile
    try:
        if client.voice_profile:
            vp = client.voice_profile
            pd = vp.profile_data or {}
            tone = pd.get("tone", "not set")
            formality = pd.get("formality", "not set")
            reading_ease = pd.get("reading_ease", "?")
            parts.append(f"Voice: tone={tone}, formality={formality}, reading ease={reading_ease}")
    except Exception:
        pass

    # Pending drafts
    try:
        from sophia.approval.service import get_approval_queue

        pending = get_approval_queue(db, client_id=client_id)
        if pending:
            parts.append(f"\nPending drafts ({len(pending)}):")
            for draft in pending[:3]:
                preview = (draft.copy or "")[:120]
                parts.append(f"  - Draft #{draft.id}: {preview}...")
    except Exception:
        pass

    # Recent learnings
    try:
        from sophia.agent.learning import get_active_learnings

        learnings = get_active_learnings(db, client_id, limit=5)
        if learnings:
            parts.append("\nRecent learnings:")
            for lr in learnings:
                parts.append(f"  - [{lr.learning_type}] {lr.content[:150]}")
    except Exception:
        pass

    sections.append("\n".join(parts))


# ---------------------------------------------------------------------------
# Action execution
# ---------------------------------------------------------------------------


async def _execute_action(
    db: Session,
    action: dict,
    client_context_id: Optional[int],
) -> AsyncGenerator[dict, None]:
    """Dispatch an action tag to the appropriate service function."""
    verb = action["verb"]
    args = action["args"]

    if verb == "switch_client":
        async for chunk in _action_switch_client(db, args):
            yield chunk

    elif verb == "approve":
        async for chunk in _action_approve(db, args):
            yield chunk

    elif verb == "reject":
        async for chunk in _action_reject(db, args):
            yield chunk

    elif verb == "skip":
        async for chunk in _action_skip(db, args):
            yield chunk

    elif verb == "trigger_cycle":
        async for chunk in _action_trigger_cycle(db, args):
            yield chunk

    elif verb == "create_client":
        async for chunk in _action_create_client(db, args):
            yield chunk

    elif verb == "update_client":
        async for chunk in _action_update_client(db, args):
            yield chunk

    elif verb == "archive_client":
        async for chunk in _action_archive_client(db, args):
            yield chunk

    elif verb == "add_voice_material":
        async for chunk in _action_add_voice_material(db, args):
            yield chunk

    elif verb == "add_intelligence":
        async for chunk in _action_add_intelligence(db, args):
            yield chunk

    elif verb == "learn":
        async for chunk in _action_learn(db, args, client_context_id):
            yield chunk

    else:
        logger.warning("Unknown action verb: %s", verb)


async def _action_switch_client(
    db: Session, args: list[str]
) -> AsyncGenerator[dict, None]:
    """Execute switch_client action with fuzzy matching."""
    client_name = args[0] if args else ""
    if not client_name:
        return

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
                "type": "context",
                "client_id": best_match.id,
                "client_name": best_match.name,
            }
        else:
            yield {
                "type": "text",
                "content": f"(Could not find a client matching '{client_name}'.)",
            }
    except Exception as e:
        logger.exception("switch_client action failed")
        yield {"type": "text", "content": f"(Client switch failed: {e})"}


async def _action_approve(
    db: Session, args: list[str]
) -> AsyncGenerator[dict, None]:
    """Execute approve action on a draft."""
    try:
        draft_id = int(args[0])
        from sophia.approval.service import approve_draft

        approve_draft(db, draft_id, actor="operator:chat")
        db.commit()
    except (ValueError, IndexError):
        yield {"type": "text", "content": "(Invalid draft ID for approve action.)"}
    except Exception as e:
        logger.exception("approve action failed")
        yield {"type": "text", "content": f"(Approve failed: {e})"}


async def _action_reject(
    db: Session, args: list[str]
) -> AsyncGenerator[dict, None]:
    """Execute reject action on a draft."""
    try:
        draft_id = int(args[0])
        reason = args[1] if len(args) > 1 else "Rejected via chat"
        from sophia.approval.service import reject_draft

        reject_draft(db, draft_id, guidance=reason, actor="operator:chat")
        db.commit()
    except (ValueError, IndexError):
        yield {"type": "text", "content": "(Invalid draft ID for reject action.)"}
    except Exception as e:
        logger.exception("reject action failed")
        yield {"type": "text", "content": f"(Reject failed: {e})"}


async def _action_skip(
    db: Session, args: list[str]
) -> AsyncGenerator[dict, None]:
    """Execute skip action on a draft."""
    try:
        draft_id = int(args[0])
        from sophia.approval.service import skip_draft

        skip_draft(db, draft_id, actor="operator:chat")
        db.commit()
    except (ValueError, IndexError):
        yield {"type": "text", "content": "(Invalid draft ID for skip action.)"}
    except Exception as e:
        logger.exception("skip action failed")
        yield {"type": "text", "content": f"(Skip failed: {e})"}


async def _action_trigger_cycle(
    db: Session, args: list[str]
) -> AsyncGenerator[dict, None]:
    """Execute trigger_cycle action for a client."""
    try:
        client_id = int(args[0])
        from sophia.orchestrator.chat import _create_and_fire_cycle

        cycle_id = _create_and_fire_cycle(db, client_id)
        yield {
            "type": "text",
            "content": f"(Cycle #{cycle_id} started for client {client_id}.)",
        }
    except (ValueError, IndexError):
        yield {"type": "text", "content": "(Invalid client ID for cycle trigger.)"}
    except Exception as e:
        logger.exception("trigger_cycle action failed")
        yield {"type": "text", "content": f"(Cycle trigger failed: {e})"}


async def _action_create_client(
    db: Session, args: list[str]
) -> AsyncGenerator[dict, None]:
    """Execute create_client action."""
    client_name = args[0] if args else ""
    industry = args[1] if len(args) > 1 else ""
    if not client_name or not industry:
        yield {"type": "text", "content": "(Create client requires name and industry.)"}
        return

    try:
        from sophia.intelligence.schemas import ClientCreate
        from sophia.intelligence.service import ClientService

        data = ClientCreate(name=client_name, industry=industry)
        client = ClientService.create_client(db, data)
        # Auto-switch context to the new client
        yield {
            "type": "context",
            "client_id": client.id,
            "client_name": client.name,
        }
    except Exception as e:
        logger.exception("create_client action failed")
        yield {"type": "text", "content": f"(Client creation failed: {e})"}


async def _action_update_client(
    db: Session, args: list[str]
) -> AsyncGenerator[dict, None]:
    """Execute update_client action.

    Args format: ["CLIENT_ID", "field=value", "field=value", ...]
    """
    if not args:
        yield {"type": "text", "content": "(Update client requires a client ID.)"}
        return

    try:
        client_id = int(args[0])
    except ValueError:
        yield {"type": "text", "content": f"(Invalid client ID: {args[0]}.)"}
        return

    # Parse field=value pairs from remaining args
    update_fields: dict = {}
    for pair in args[1:]:
        if "=" not in pair:
            continue
        key, _, value = pair.partition("=")
        key = key.strip()
        value = value.strip()
        # Coerce geography_radius_km to int
        if key == "geography_radius_km":
            try:
                update_fields[key] = int(value)
            except ValueError:
                yield {"type": "text", "content": f"(Invalid integer for {key}: {value}.)"}
                return
        else:
            update_fields[key] = value

    if not update_fields:
        yield {"type": "text", "content": "(No fields to update. Use FIELD=VALUE pairs.)"}
        return

    try:
        from sophia.intelligence.schemas import ClientUpdate
        from sophia.intelligence.service import ClientService

        data = ClientUpdate(**update_fields)
        client = ClientService.update_client(db, client_id, data)
        yield {
            "type": "text",
            "content": (
                f"(Updated {client.name}: "
                f"{', '.join(f'{k}={v}' for k, v in update_fields.items())}. "
                f"Profile now {client.profile_completeness_pct}% complete.)"
            ),
        }
    except Exception as e:
        logger.exception("update_client action failed")
        yield {"type": "text", "content": f"(Client update failed: {e})"}


async def _action_archive_client(
    db: Session, args: list[str]
) -> AsyncGenerator[dict, None]:
    """Execute archive_client action."""
    if not args:
        yield {"type": "text", "content": "(Archive client requires a client ID.)"}
        return

    try:
        client_id = int(args[0])
    except ValueError:
        yield {"type": "text", "content": f"(Invalid client ID: {args[0]}.)"}
        return

    try:
        from sophia.intelligence.service import ClientService

        result = ClientService.archive_client(db, client_id)
        yield {
            "type": "text",
            "content": (
                f"(Archived {result['name']}. "
                f"ICP knowledge retained: {result['icp_knowledge_retained']}.)"
            ),
        }
    except Exception as e:
        logger.exception("archive_client action failed")
        yield {"type": "text", "content": f"(Archive failed: {e})"}


async def _action_add_voice_material(
    db: Session, args: list[str]
) -> AsyncGenerator[dict, None]:
    """Execute add_voice_material action.

    Args format: [CLIENT_ID, SOURCE_TYPE, CONTENT...]
    Content may contain colons, so rejoin args[2:].
    """
    if len(args) < 3:
        yield {"type": "text", "content": "(Voice material requires client ID, source type, and content.)"}
        return

    try:
        client_id = int(args[0])
    except ValueError:
        yield {"type": "text", "content": f"(Invalid client ID: {args[0]}.)"}
        return

    source_type = args[1]
    content = ":".join(args[2:])

    try:
        from sophia.intelligence.schemas import VoiceMaterialCreate
        from sophia.intelligence.voice import VoiceService

        data = VoiceMaterialCreate(
            client_id=client_id,
            source_type=source_type,
            content=content,
        )
        material = VoiceService.add_material(db, data)
        yield {
            "type": "text",
            "content": (
                f"(Stored voice material #{material.id} for client {client_id}: "
                f"{source_type}, {len(content)} chars.)"
            ),
        }
    except Exception as e:
        logger.exception("add_voice_material action failed")
        yield {"type": "text", "content": f"(Voice material failed: {e})"}


async def _bg_add_intelligence(
    db: Session,
    client_id: int,
    domain: str,
    fact: str,
    source: str,
    confidence: float,
) -> None:
    """Background task for add_intelligence (embedding is slow on first call)."""
    try:
        from sophia.intelligence.service import add_intelligence

        await add_intelligence(
            db,
            client_id=client_id,
            domain=domain,
            fact=fact,
            source=source,
            confidence=confidence,
        )
    except Exception:
        logger.exception(
            "Background add_intelligence failed: client=%d domain=%s",
            client_id,
            domain,
        )


async def _action_add_intelligence(
    db: Session, args: list[str]
) -> AsyncGenerator[dict, None]:
    """Execute add_intelligence action.

    Args format: [CLIENT_ID, DOMAIN, FACT...]
    Fact may contain colons, so rejoin args[2:].
    Fire-and-forget: SQLite write + embedding happen in background
    so the SSE stream isn't blocked by model loading.
    """
    if len(args) < 3:
        yield {"type": "text", "content": "(Intelligence entry requires client ID, domain, and fact.)"}
        return

    try:
        client_id = int(args[0])
    except ValueError:
        yield {"type": "text", "content": f"(Invalid client ID: {args[0]}.)"}
        return

    domain = args[1]
    fact = ":".join(args[2:])

    asyncio.ensure_future(
        _bg_add_intelligence(db, client_id, domain, fact, "operator:explicit", 0.5)
    )
    yield {
        "type": "text",
        "content": (
            f"(Storing intelligence for client {client_id}: "
            f"[{domain}] {fact[:80]})"
        ),
    }


async def _action_learn(
    db: Session, args: list[str], client_context_id: Optional[int]
) -> AsyncGenerator[dict, None]:
    """Execute learn action — capture a fact from conversation into intelligence.

    Args format: [DOMAIN, FACT...]
    Uses active client context (no CLIENT_ID in args).
    Fire-and-forget so the SSE stream isn't blocked by model loading.
    """
    if not args or len(args) < 2:
        yield {"type": "text", "content": "(Learn requires domain and fact.)"}
        return

    if not client_context_id:
        yield {"type": "text", "content": "(Cannot learn without an active client context.)"}
        return

    domain = args[0]
    fact = ":".join(args[1:])

    asyncio.ensure_future(
        _bg_add_intelligence(
            db, client_context_id, domain, fact, "operator:conversation", 0.7
        )
    )
    yield {
        "type": "text",
        "content": f"(Learned: [{domain}] {fact[:80]})",
    }


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------


def _fallback_response(message: str) -> str:
    """Minimal fallback when Claude CLI is unavailable."""
    return (
        "I'm having trouble connecting to my reasoning engine right now. "
        "You can still use the tabs above for approvals, client management, "
        "and content review. I'll be back shortly."
    )


# ---------------------------------------------------------------------------
# Tool permissions for -p (print) mode
# ---------------------------------------------------------------------------

# In -p mode, tools are silently denied unless explicitly allowed.
# Grant all built-in tools + MCP tool wildcards so Claude can reason fully.
_ALLOWED_TOOLS = ",".join([
    "Read", "Edit", "Write",
    "Bash", "Glob", "Grep",
    "WebSearch", "WebFetch",
    "NotebookEdit",
    "mcp__plugin_playwright_playwright__*",
])

# ---------------------------------------------------------------------------
# Main streaming entry point
# ---------------------------------------------------------------------------


async def stream_claude_response(
    db: Session,
    message: str,
    client_context_id: Optional[int] = None,
) -> AsyncGenerator[dict, None]:
    """Stream a response from Claude CLI for a chat message.

    Spawns `claude -p --output-format stream-json` as a subprocess, feeds
    the operator's message, and streams text deltas back as SSE chunks.
    After the full response is collected, parses action tags and executes them.

    Yields dicts with type/content keys for SSE events.
    """
    system_prompt = build_system_prompt(db, client_context_id)

    # Build clean env: only strip the nested-session guard vars.
    # Preserve everything else (auth tokens, PATH, HOME, etc.).
    _STRIP_VARS = {"CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"}
    env = {k: v for k, v in os.environ.items() if k not in _STRIP_VARS}

    cmd = [
        "claude",
        "-p",
        "--verbose",
        "--output-format", "stream-json",
        "--max-turns", "25",
        "--allowedTools", _ALLOWED_TOOLS,
        "--system-prompt", system_prompt,
        message,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
    except FileNotFoundError:
        logger.error("claude CLI not found in PATH")
        yield {"type": "text", "content": _fallback_response(message)}
        return
    except Exception:
        logger.exception("Failed to spawn claude CLI")
        yield {"type": "text", "content": _fallback_response(message)}
        return

    # Stream stdout line-by-line (NDJSON), with timeout
    full_text_parts: list[str] = []
    seen_assistant: list = []  # mutable tracker for _extract_text_from_event
    try:
        async with asyncio.timeout(1800):
            assert proc.stdout is not None
            async for raw_line in proc.stdout:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Extract text from stream-json events
                text_chunk = _extract_text_from_event(event, seen_assistant)
                if text_chunk:
                    full_text_parts.append(text_chunk)
                    yield {"type": "text", "content": text_chunk}

    except TimeoutError:
        logger.error("Claude CLI timed out after 1800s")
        proc.kill()
        if not full_text_parts:
            yield {"type": "text", "content": _fallback_response(message)}
            return
    except Exception:
        logger.exception("Error reading Claude CLI output")
        if not full_text_parts:
            yield {"type": "text", "content": _fallback_response(message)}
            return

    # Wait for process to finish and log any stderr
    try:
        await asyncio.wait_for(proc.wait(), timeout=5)
    except TimeoutError:
        proc.kill()

    if proc.stderr:
        stderr_bytes = await proc.stderr.read()
        stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()
        if stderr_text:
            logger.warning("Claude CLI stderr: %s", stderr_text[:500])

    # Parse action tags from full response
    full_text = "".join(full_text_parts)
    clean_text, actions = _parse_action_tags(full_text)

    # If action tags were found, execute them
    for action in actions:
        async for chunk in _execute_action(db, action, client_context_id):
            yield chunk


def _extract_text_from_event(event: dict, seen_assistant: list) -> Optional[str]:
    """Extract text content from a Claude stream-json event.

    The --verbose stream-json format emits NDJSON with these event types:
    - type "assistant": message.content[] array with text blocks
    - type "result": result field with full text (used as fallback only)
    - type "system": init, hooks, etc (ignored)

    seen_assistant tracks whether we already got text from an assistant event,
    so we don't double-yield from the result event.
    """
    # assistant events — primary text source
    if event.get("type") == "assistant":
        message = event.get("message", {})
        content_blocks = message.get("content", [])
        parts = []
        for block in content_blocks:
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
        if parts:
            text = "".join(parts)
            seen_assistant.append(True)
            return text

    # result event — fallback if no assistant events yielded text
    if event.get("type") == "result" and not seen_assistant:
        result_text = event.get("result", "")
        if isinstance(result_text, str) and result_text:
            return result_text

    return None
