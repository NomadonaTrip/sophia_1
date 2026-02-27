"""Sophia FastAPI application assembly.

Wires routers, DB dependencies, and lifespan management.
Run: uvicorn sophia.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sophia.approval.router import approval_router, events_router
from sophia.content.router import content_router
from sophia.research.router import router as research_router

app = FastAPI(title="Sophia", version="0.1.0")

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
