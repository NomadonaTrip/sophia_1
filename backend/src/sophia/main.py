"""Sophia FastAPI application assembly.

Wires routers, DB dependencies, lifespan management (APScheduler,
Telegram bot), and CORS middleware.
Run: uvicorn sophia.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from sophia.analytics.router import analytics_router
from sophia.approval.router import approval_router, events_router
from sophia.content.router import content_router
from sophia.publishing.scheduler import create_scheduler
from sophia.publishing.stale_monitor import register_stale_monitor
from sophia.research.router import router as research_router


def _session_factory():
    """Lazy session factory -- module-level so APScheduler can pickle it."""
    from sophia.db.engine import SessionLocal
    return SessionLocal()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: start/stop APScheduler and Telegram bot.

    - APScheduler: separate unencrypted SQLite job store (SQLCipher incompatible)
    - Telegram bot: webhook mode, registered as notification channel
    """
    # Start APScheduler with separate unencrypted SQLite job store
    # Use same data directory as main DB, but unencrypted (APScheduler incompatible with SQLCipher)
    from sophia.config import get_settings
    import os

    settings = get_settings()
    scheduler_dir = os.path.dirname(settings.db_path)
    os.makedirs(scheduler_dir, exist_ok=True)
    scheduler_db_url = f"sqlite:///{scheduler_dir}/scheduler.db"
    scheduler = create_scheduler(scheduler_db_url)
    scheduler.start()

    # Register stale content monitor (runs every 30 min)
    register_stale_monitor(scheduler, _session_factory)

    # Register daily metric pull (6 AM operator timezone)
    from sophia.analytics.collector import register_daily_metric_pull

    register_daily_metric_pull(scheduler, _session_factory, settings)

    app.state.scheduler = scheduler

    # Initialize Telegram bot if token configured
    if settings.telegram_bot_token:
        from sophia.telegram.bot import build_telegram_app
        from sophia.publishing.notifications import notification_service

        tg_app = await build_telegram_app(
            token=settings.telegram_bot_token,
            webhook_url=f"{settings.base_url}/api/telegram/webhook",
            session_factory=_session_factory,
        )
        await tg_app.initialize()
        await tg_app.start()

        # Store scheduler reference in bot_data for /resume command
        tg_app.bot_data["scheduler"] = scheduler

        app.state.telegram = tg_app

        # Register Telegram as a notification channel for publish events
        async def telegram_notification_handler(event_type: str, data: dict):
            """Forward publishing events to Telegram operator chat."""
            chat_id = settings.telegram_chat_id
            if not chat_id:
                return
            bot = tg_app.bot
            if event_type == "publish_complete":
                text = (
                    f"Published! {data.get('platform', '').title()}\n"
                    f"{data.get('platform_url', '')}"
                )
                # Include a "Recover" inline button on publish confirmations
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup

                keyboard = [
                    [
                        InlineKeyboardButton(
                            "Recover",
                            callback_data=f"recover_{data['draft_id']}",
                        )
                    ]
                ]
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
            elif event_type == "publish_failed":
                text = (
                    f"Publishing FAILED for draft #{data.get('draft_id')}: "
                    f"{data.get('error', 'unknown')}"
                )
                await bot.send_message(chat_id=chat_id, text=text)
            elif event_type == "recovery_complete":
                text = (
                    f"Recovery {data.get('status', '')} for "
                    f"{data.get('platform', '').title()} post "
                    f"(draft #{data.get('draft_id')})"
                )
                await bot.send_message(chat_id=chat_id, text=text)
            elif event_type == "content_stale":
                text = (
                    f"Content stale: draft #{data.get('draft_id')} "
                    f"has been in review for {data.get('hours_stale', '?')} hours"
                )
                await bot.send_message(chat_id=chat_id, text=text)

        notification_service.register_channel(telegram_notification_handler)

    yield

    # Shutdown Telegram bot
    if hasattr(app.state, "telegram"):
        await app.state.telegram.stop()
        await app.state.telegram.shutdown()

    # Shutdown APScheduler
    app.state.scheduler.shutdown(wait=False)


app = FastAPI(title="Sophia", version="0.1.0", lifespan=lifespan)

# CORS for frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(approval_router)
app.include_router(events_router)
app.include_router(content_router)
app.include_router(research_router)
app.include_router(analytics_router)


# Telegram webhook endpoint
@app.post("/api/telegram/webhook")
async def telegram_webhook(request: Request):
    """Receive Telegram updates via webhook."""
    if not hasattr(request.app.state, "telegram"):
        raise HTTPException(503, "Telegram bot not configured")

    from telegram import Update

    json_data = await request.json()
    update = Update.de_json(json_data, request.app.state.telegram.bot)
    await request.app.state.telegram.process_update(update)
    return {"ok": True}


# DB dependency wiring happens here in production
# For now, routers use placeholder _get_db() that raises NotImplementedError
# Actual wiring with get_engine() happens when the full app is assembled
