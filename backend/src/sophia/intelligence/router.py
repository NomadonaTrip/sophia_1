"""Client API router.

Provides GET/POST/PATCH /api/clients to serve the frontend PortfolioGrid
with real client data from the database, bridging backend model fields
to the frontend ClientData shape.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from sophia.exceptions import ClientNotFoundError, DuplicateClientError
from sophia.intelligence.models import Client, VoiceProfile
from sophia.intelligence.schemas import (
    ClientCreate,
    ClientUpdate,
    IntelligenceEntryBody,
    VoiceMaterialBody,
)
from sophia.intelligence.service import ClientService

client_router = APIRouter(prefix="/api", tags=["clients"])


def _get_db():
    """Yield a SQLAlchemy session. Lazy-imports engine to avoid slow NTFS imports at startup."""
    from sophia.db.engine import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


def _derive_status(profile_completeness_pct: int) -> str:
    """Map profile completeness to frontend status string."""
    if profile_completeness_pct >= 80:
        return "cruising"
    if profile_completeness_pct >= 40:
        return "calibrating"
    return "attention"


def _client_to_dict(client: Client) -> dict:
    """Bridge a Client model to the frontend ClientData shape."""
    voice_match_pct = 0
    if client.voice_profile is not None:
        voice_match_pct = client.voice_profile.overall_confidence_pct

    return {
        "id": client.id,
        "name": client.name,
        "status": _derive_status(client.profile_completeness_pct),
        "postCount": 0,
        "engagementRate": 0.0,
        "trend": "flat",
        "voiceMatchPct": voice_match_pct,
        "sparkline": [0, 0, 0, 0, 0, 0],
    }


def _ensure_voice_profile(db: Session, client: Client) -> None:
    """Lazy-create a voice profile for clients that don't have one."""
    if client.voice_profile is not None:
        return
    try:
        from sophia.intelligence.voice import VoiceService

        try:
            profile_data = VoiceService.build_voice_profile(db, client.id)
        except Exception:
            profile_data = VoiceService.create_fallback_profile(
                db, client.id, client.industry or "general"
            )
        VoiceService.save_voice_profile(db, client.id, profile_data)
        db.refresh(client)
    except Exception:
        pass


@client_router.get("/clients")
def list_clients(db: Session = Depends(_get_db)) -> list[dict]:
    """Return all active clients shaped for the frontend ClientData interface."""
    clients = ClientService.list_clients(db)
    for c in clients:
        _ensure_voice_profile(db, c)
    return [_client_to_dict(c) for c in clients]


@client_router.get("/clients/{client_id}")
def get_client(client_id: int, db: Session = Depends(_get_db)) -> dict:
    """Return a single client shaped for the frontend ClientData interface."""
    try:
        client = ClientService.get_client(db, client_id)
    except ClientNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message)
    _ensure_voice_profile(db, client)
    return _client_to_dict(client)


@client_router.post("/clients")
def create_client(data: ClientCreate, db: Session = Depends(_get_db)) -> dict:
    """Create a new client. Returns frontend ClientData shape."""
    try:
        client = ClientService.create_client(db, data)
    except DuplicateClientError as exc:
        raise HTTPException(status_code=409, detail=exc.message)
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail=f"Database busy: {exc}")
    return _client_to_dict(client)


@client_router.patch("/clients/{client_id}")
def update_client(
    client_id: int, data: ClientUpdate, db: Session = Depends(_get_db)
) -> dict:
    """Update a client profile. Returns updated frontend ClientData shape."""
    try:
        client = ClientService.update_client(db, client_id, data)
    except ClientNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message)
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail=f"Database busy: {exc}")
    return _client_to_dict(client)


@client_router.post("/clients/{client_id}/archive")
def archive_client(client_id: int, db: Session = Depends(_get_db)) -> dict:
    """Archive a client. Extracts ICP knowledge before archiving."""
    try:
        result = ClientService.archive_client(db, client_id)
    except ClientNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message)
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail=f"Database busy: {exc}")
    return result


# -- Voice Material -----------------------------------------------------------


@client_router.post("/clients/{client_id}/voice/materials")
def add_voice_material(
    client_id: int, body: VoiceMaterialBody, db: Session = Depends(_get_db)
) -> dict:
    """Ingest voice source material for a client."""
    # Validate client exists
    try:
        ClientService.get_client(db, client_id)
    except ClientNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message)

    from sophia.intelligence.schemas import VoiceMaterialCreate
    from sophia.intelligence.voice import VoiceService

    data = VoiceMaterialCreate(client_id=client_id, **body.model_dump())
    material = VoiceService.add_material(db, data)

    # Rebuild voice profile from all materials
    try:
        profile_data = VoiceService.build_voice_profile(db, client_id)
        VoiceService.save_voice_profile(db, client_id, profile_data)
    except Exception:
        pass  # Material is stored; profile rebuild is non-critical

    return {
        "id": material.id,
        "client_id": material.client_id,
        "source_type": material.source_type,
        "content_length": len(material.content),
    }


# -- Intelligence Entry -------------------------------------------------------


@client_router.post("/clients/{client_id}/intelligence")
async def add_intelligence_entry(
    client_id: int, body: IntelligenceEntryBody, db: Session = Depends(_get_db)
) -> dict:
    """Add an intelligence entry for a client."""
    # Validate client exists
    try:
        ClientService.get_client(db, client_id)
    except ClientNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message)

    from sophia.intelligence.service import add_intelligence

    entry = await add_intelligence(
        db,
        client_id=client_id,
        domain=body.domain,
        fact=body.fact,
        source=body.source,
        confidence=body.confidence,
    )
    return {
        "id": entry.id,
        "client_id": entry.client_id,
        "domain": entry.domain.value if hasattr(entry.domain, "value") else entry.domain,
        "fact": entry.fact,
        "confidence": entry.confidence,
    }
