"""Telegram callback/command handlers for content approval.

All handlers call the SAME approval service as the web app -- no
duplicate business logic. DB sessions are created from the session
factory stored in ``context.bot_data["session_factory"]`` (set during
bot initialisation in ``bot.py``).

Handlers:
  - approve / reject / edit / skip callbacks via inline keyboards
  - recovery callback (on published-post confirmations)
  - /pause, /resume global commands
  - Free-text reply handler for rejection guidance and inline edits

Note: ``telegram`` imports are lazy (inside functions) so the module
can be imported without python-telegram-bot installed (for testing).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sophia.telegram.formatters import format_draft_message

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper: obtain a DB session from bot_data
# ---------------------------------------------------------------------------


def _get_db(context: Any) -> "Session":
    """Create a DB session from the factory stored in bot_data."""
    factory = context.bot_data.get("session_factory")
    if factory is None:
        raise RuntimeError(
            "session_factory not set in bot_data. "
            "Ensure build_telegram_app() stores it during initialisation."
        )
    return factory()


# ---------------------------------------------------------------------------
# Inline-keyboard button helpers
# ---------------------------------------------------------------------------


def build_draft_keyboard(draft_id: int) -> Any:
    """Build the standard Approve / Edit / Reject / Skip inline keyboard."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    keyboard = [
        [
            InlineKeyboardButton("Approve", callback_data=f"approve_{draft_id}"),
            InlineKeyboardButton("Edit", callback_data=f"edit_{draft_id}"),
        ],
        [
            InlineKeyboardButton("Reject", callback_data=f"reject_{draft_id}"),
            InlineKeyboardButton("Skip", callback_data=f"skip_{draft_id}"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


async def send_content_for_review(bot: Any, chat_id: str, draft: Any, client_name: str = "") -> None:
    """Send a content draft with inline keyboard buttons."""
    text = format_draft_message(draft, client_name=client_name)
    reply_markup = build_draft_keyboard(draft.id)
    await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# Callback query handlers (inline keyboard buttons)
# ---------------------------------------------------------------------------


async def approval_callback(update: Any, context: Any) -> None:
    """Handle Approve button press."""
    query = update.callback_query
    await query.answer()
    _, draft_id_str = query.data.split("_", 1)
    draft_id = int(draft_id_str)

    db = _get_db(context)
    try:
        from sophia.approval.service import approve_draft

        draft = approve_draft(db, draft_id, actor="operator:telegram")
        db.commit()
        scheduled = draft.suggested_post_time
        time_str = scheduled.strftime("%b %d, %I:%M %p") if scheduled else "auto"
        await query.edit_message_text(f"Approved! Scheduled for {time_str}")
    except Exception as exc:
        db.rollback()
        logger.error("Telegram approve failed for draft %d: %s", draft_id, exc)
        await query.edit_message_text(f"Approval failed: {exc}")
    finally:
        db.close()


async def reject_callback(update: Any, context: Any) -> None:
    """Handle Reject button press. Prompts for guidance via text reply."""
    query = update.callback_query
    await query.answer()
    _, draft_id_str = query.data.split("_", 1)
    draft_id = int(draft_id_str)

    # Store draft_id in context for the reply handler
    context.user_data["pending_rejection"] = draft_id
    await query.edit_message_text(
        f"Rejecting draft #{draft_id}. Reply with your feedback "
        f"(e.g., 'too formal' or specific guidance):"
    )


async def edit_callback(update: Any, context: Any) -> None:
    """Handle Edit button. Operator replies with edited text."""
    query = update.callback_query
    await query.answer()
    _, draft_id_str = query.data.split("_", 1)
    context.user_data["pending_edit"] = int(draft_id_str)
    await query.edit_message_text("Reply with the edited version of this post:")


async def skip_callback(update: Any, context: Any) -> None:
    """Handle Skip button press."""
    query = update.callback_query
    await query.answer()
    _, draft_id_str = query.data.split("_", 1)
    draft_id = int(draft_id_str)

    db = _get_db(context)
    try:
        from sophia.approval.service import skip_draft

        skip_draft(db, draft_id, actor="operator:telegram")
        db.commit()
        await query.edit_message_text("Skipped. Moving to next post.")
    except Exception as exc:
        db.rollback()
        logger.error("Telegram skip failed for draft %d: %s", draft_id, exc)
        await query.edit_message_text(f"Skip failed: {exc}")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Recovery handler
# ---------------------------------------------------------------------------


async def recovery_callback(update: Any, context: Any) -> None:
    """Handle recovery inline button on published post confirmations."""
    query = update.callback_query
    await query.answer()
    _, draft_id_str = query.data.split("_", 1)
    context.user_data["pending_recovery"] = int(draft_id_str)
    await query.edit_message_text("Why should this post be recovered? Reply with reason:")


# ---------------------------------------------------------------------------
# Free-text reply handlers
# ---------------------------------------------------------------------------


async def text_reply_handler(update: Any, context: Any) -> None:
    """Route free-text replies to the appropriate pending action.

    Checks for pending_rejection, pending_edit, pending_recovery in order.
    """
    if "pending_rejection" in context.user_data:
        await _handle_rejection_guidance(update, context)
    elif "pending_edit" in context.user_data:
        await _handle_edit_text(update, context)
    elif "pending_recovery" in context.user_data:
        await _handle_recovery_reason(update, context)
    # Ignore other free text (no pending action)


async def _handle_rejection_guidance(update: Any, context: Any) -> None:
    """Handle text reply as rejection guidance."""
    draft_id = context.user_data.pop("pending_rejection")
    guidance = update.message.text

    db = _get_db(context)
    try:
        from sophia.approval.service import reject_draft

        reject_draft(db, draft_id, guidance=guidance, actor="operator:telegram")
        db.commit()
        await update.message.reply_text(
            f"Rejected with feedback: '{guidance}'. Regenerating..."
        )
    except Exception as exc:
        db.rollback()
        logger.error("Telegram reject failed for draft %d: %s", draft_id, exc)
        await update.message.reply_text(f"Rejection failed: {exc}")
    finally:
        db.close()


async def _handle_edit_text(update: Any, context: Any) -> None:
    """Handle text reply as edited copy."""
    draft_id = context.user_data.pop("pending_edit")
    new_copy = update.message.text

    db = _get_db(context)
    try:
        from sophia.approval.service import edit_draft

        edit_draft(db, draft_id, new_copy, actor="operator:telegram")
        db.commit()
        await update.message.reply_text("Updated. Here's the new version -- Approve?")
    except Exception as exc:
        db.rollback()
        logger.error("Telegram edit failed for draft %d: %s", draft_id, exc)
        await update.message.reply_text(f"Edit failed: {exc}")
    finally:
        db.close()


async def _handle_recovery_reason(update: Any, context: Any) -> None:
    """Handle text reply as recovery reason."""
    draft_id = context.user_data.pop("pending_recovery")
    reason = update.message.text

    db = _get_db(context)
    try:
        from sophia.publishing.recovery import recover_content

        log = await recover_content(
            db, draft_id, reason=reason, triggered_by="operator:telegram"
        )
        db.commit()

        from sophia.telegram.formatters import format_recovery_result

        await update.message.reply_text(format_recovery_result(log))
    except Exception as exc:
        db.rollback()
        logger.error("Telegram recovery failed for draft %d: %s", draft_id, exc)
        await update.message.reply_text(f"Recovery failed: {exc}")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Global pause/resume commands
# ---------------------------------------------------------------------------


async def global_pause_handler(update: Any, context: Any) -> None:
    """Handle /pause command -- pause all scheduled publishing."""
    db = _get_db(context)
    try:
        from sophia.publishing.scheduler import pause_all

        await pause_all(db)
        db.commit()
        await update.message.reply_text(
            "All scheduled publishing PAUSED. Use /resume to restart."
        )
    except Exception as exc:
        db.rollback()
        logger.error("Telegram pause failed: %s", exc)
        await update.message.reply_text(f"Pause failed: {exc}")
    finally:
        db.close()


async def global_resume_handler(update: Any, context: Any) -> None:
    """Handle /resume command -- requires confirmation via inline button."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    keyboard = [
        [
            InlineKeyboardButton(
                "Confirm Resume", callback_data="confirm_resume"
            ),
            InlineKeyboardButton("Cancel", callback_data="cancel_resume"),
        ]
    ]
    await update.message.reply_text(
        "Resume all scheduled publishing?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def resume_confirm_callback(update: Any, context: Any) -> None:
    """Handle the Confirm Resume inline button."""
    query = update.callback_query
    await query.answer()

    db = _get_db(context)
    try:
        from sophia.publishing.scheduler import resume_all

        # resume_all requires the scheduler instance
        scheduler = context.bot_data.get("scheduler")
        await resume_all(db, scheduler)
        db.commit()
        await query.edit_message_text("Publishing RESUMED. All queued posts restored.")
    except Exception as exc:
        db.rollback()
        logger.error("Telegram resume failed: %s", exc)
        await query.edit_message_text(f"Resume failed: {exc}")
    finally:
        db.close()


async def resume_cancel_callback(update: Any, context: Any) -> None:
    """Handle the Cancel Resume inline button."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Resume cancelled. Publishing remains paused.")


# ---------------------------------------------------------------------------
# /start command
# ---------------------------------------------------------------------------


async def start_handler(update: Any, context: Any) -> None:
    """Handle /start command -- welcome message."""
    await update.message.reply_text(
        "Hey! I'm Sophia, your content approval assistant.\n\n"
        "I'll send you content drafts with inline buttons to Approve, "
        "Edit, Reject, or Skip.\n\n"
        "Commands:\n"
        "/pause -- Pause all scheduled publishing\n"
        "/resume -- Resume publishing (requires confirmation)"
    )
