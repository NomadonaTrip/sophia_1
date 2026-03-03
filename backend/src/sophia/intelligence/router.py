"""Client API router.

Provides GET /api/clients to serve the frontend PortfolioGrid with real
client data from the database, bridging backend model fields to the
frontend ClientData shape.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from sophia.intelligence.models import Client, VoiceProfile
from sophia.intelligence.service import ClientService

client_router = APIRouter(prefix="/api", tags=["clients"])


def _get_db():
    """Yield a SQLAlchemy session. Lazy-imports engine to avoid slow NTFS imports at startup."""
    from sophia.db.engine import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _derive_status(profile_completeness_pct: int) -> str:
    """Map profile completeness to frontend status string."""
    if profile_completeness_pct >= 80:
        return "cruising"
    if profile_completeness_pct >= 40:
        return "calibrating"
    return "attention"


@client_router.get("/clients")
def list_clients(db: Session = Depends(_get_db)) -> list[dict]:
    """Return all active clients shaped for the frontend ClientData interface."""
    clients = ClientService.list_clients(db)

    result = []
    for client in clients:
        # Get voice profile confidence if it exists
        voice_match_pct = 0
        if client.voice_profile is not None:
            voice_match_pct = client.voice_profile.overall_confidence_pct

        result.append({
            "id": client.id,
            "name": client.name,
            "status": _derive_status(client.profile_completeness_pct),
            "postCount": 0,
            "engagementRate": 0.0,
            "trend": "flat",
            "voiceMatchPct": voice_match_pct,
            "sparkline": [0, 0, 0, 0, 0, 0],
        })

    return result
