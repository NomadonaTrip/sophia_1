"""Telegram Application builder with webhook mode.

Builds a python-telegram-bot Application configured for webhook mode
(no polling). Registers all approval handlers and stores the DB
session factory in ``bot_data`` for use by handler functions.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from sophia.telegram.handlers import (
    approval_callback,
    edit_callback,
    global_pause_handler,
    global_resume_handler,
    recovery_callback,
    reject_callback,
    resume_cancel_callback,
    resume_confirm_callback,
    skip_callback,
    start_handler,
    text_reply_handler,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


async def build_telegram_app(
    token: str,
    webhook_url: str,
    session_factory: Callable | None = None,
) -> Application:
    """Build a Telegram Application with webhook mode (no polling).

    Args:
        token: Telegram bot token from @BotFather.
        webhook_url: Full URL for the webhook endpoint (e.g. https://example.com/api/telegram/webhook).
        session_factory: SQLAlchemy session factory for DB access in handlers.

    Returns:
        Configured Application ready for initialize() and start().
    """
    app = (
        Application.builder()
        .token(token)
        .updater(None)  # Webhook mode -- no polling
        .build()
    )

    # Store session factory in bot_data for handler access
    if session_factory is not None:
        app.bot_data["session_factory"] = session_factory

    # Register handlers in priority order
    # Command handlers
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("pause", global_pause_handler))
    app.add_handler(CommandHandler("resume", global_resume_handler))

    # Callback query handlers (inline keyboard buttons)
    app.add_handler(CallbackQueryHandler(approval_callback, pattern=r"^approve_"))
    app.add_handler(CallbackQueryHandler(reject_callback, pattern=r"^reject_"))
    app.add_handler(CallbackQueryHandler(edit_callback, pattern=r"^edit_"))
    app.add_handler(CallbackQueryHandler(skip_callback, pattern=r"^skip_"))
    app.add_handler(CallbackQueryHandler(recovery_callback, pattern=r"^recover_"))
    app.add_handler(
        CallbackQueryHandler(resume_confirm_callback, pattern=r"^confirm_resume$")
    )
    app.add_handler(
        CallbackQueryHandler(resume_cancel_callback, pattern=r"^cancel_resume$")
    )

    # Free-text reply handler (must be last -- catches all non-command text)
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, text_reply_handler)
    )

    # Set webhook
    await app.bot.set_webhook(url=webhook_url)

    logger.info("Telegram bot configured with webhook at %s", webhook_url)
    return app
