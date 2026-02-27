"""Sophia FastAPI application assembly.

Wires routers, DB dependencies, lifespan management (APScheduler),
and CORS middleware.
Run: uvicorn sophia.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sophia.approval.router import approval_router, events_router
from sophia.content.router import content_router
from sophia.publishing.scheduler import create_scheduler
from sophia.publishing.stale_monitor import register_stale_monitor
from sophia.research.router import router as research_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: start/stop APScheduler, register periodic jobs.

    Plan 04-05 will extend this to also start/stop the Telegram bot
    and register the Telegram notification channel.
    """
    # Start APScheduler with separate unencrypted SQLite job store
    scheduler = create_scheduler()
    scheduler.start()

    # Register stale content monitor (runs every 30 min)
    # db_session_factory placeholder -- wired when full app assembled
    # register_stale_monitor(scheduler, db_session_factory)

    app.state.scheduler = scheduler

    yield

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

# DB dependency wiring happens here in production
# For now, routers use placeholder _get_db() that raises NotImplementedError
# Actual wiring with get_engine() happens when the full app is assembled
