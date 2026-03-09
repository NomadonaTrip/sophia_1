"""Tests for client API router.

Uses FastAPI TestClient with DB dependency override. Validates
response shape matches the frontend ClientData interface and
status derivation from profile_completeness_pct.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sophia.intelligence.router import client_router, _get_db
from sophia.intelligence.models import Client, VoiceProfile
from sophia.intelligence.schemas import ClientCreate, ClientUpdate
from sophia.intelligence.service import ClientService


@pytest.fixture
def app(db_session):
    """Create FastAPI app with DB dependency override."""
    test_app = FastAPI()
    test_app.include_router(client_router)

    def override_db():
        yield db_session

    test_app.dependency_overrides[_get_db] = override_db
    return test_app


@pytest.fixture
def client(app):
    """HTTP test client."""
    return TestClient(app)


def test_list_clients_empty(client):
    """GET /api/clients returns empty list when no clients exist."""
    resp = client.get("/api/clients")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_clients_returns_real_data(client, db_session):
    """GET /api/clients returns correct shape for created clients."""
    ClientService.create_client(
        db_session, ClientCreate(name="Test Bakery", industry="Food")
    )

    resp = client.get("/api/clients")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1

    item = data[0]
    assert item["name"] == "Test Bakery"
    assert "id" in item
    assert "status" in item
    assert item["postCount"] == 0
    assert item["engagementRate"] == 0.0
    assert item["trend"] == "flat"
    assert item["voiceMatchPct"] == 10  # fallback profile: 0.15 * 0.7 = 0.105 → 10%
    assert item["sparkline"] == [0, 0, 0, 0, 0, 0]


def test_get_client_by_id(client, db_session):
    """GET /api/clients/{id} returns correct shape for a single client."""
    c = ClientService.create_client(
        db_session, ClientCreate(name="Solo Client", industry="Tech")
    )

    resp = client.get(f"/api/clients/{c.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Solo Client"
    assert data["id"] == c.id
    assert "status" in data
    assert data["postCount"] == 0


def test_get_client_by_id_not_found(client):
    """GET /api/clients/{id} with non-existent ID returns 404."""
    resp = client.get("/api/clients/99999")
    assert resp.status_code == 404


def test_client_status_derivation_attention(client, db_session):
    """Client with low completeness maps to 'attention'."""
    # A freshly created client has ~15% completeness (name + industry only)
    ClientService.create_client(
        db_session, ClientCreate(name="Low Profile Co", industry="Retail")
    )

    resp = client.get("/api/clients")
    data = resp.json()
    assert data[0]["status"] == "attention"


def test_client_status_derivation_calibrating(client, db_session):
    """Client with 40-79% completeness maps to 'calibrating'."""
    c = ClientService.create_client(
        db_session, ClientCreate(name="Mid Profile Co", industry="Retail")
    )
    # Force completeness to 50%
    c.profile_completeness_pct = 50
    db_session.flush()

    resp = client.get("/api/clients")
    data = resp.json()
    assert data[0]["status"] == "calibrating"


def test_client_status_derivation_cruising(client, db_session):
    """Client with 80%+ completeness maps to 'cruising'."""
    c = ClientService.create_client(
        db_session, ClientCreate(name="Full Profile Co", industry="Retail")
    )
    # Force completeness to 85%
    c.profile_completeness_pct = 85
    db_session.flush()

    resp = client.get("/api/clients")
    data = resp.json()
    assert data[0]["status"] == "cruising"


def test_voice_match_pct_from_profile(client, db_session):
    """voiceMatchPct reflects voice profile overall_confidence_pct."""
    c = ClientService.create_client(
        db_session, ClientCreate(name="Voice Client", industry="Music")
    )
    # Fallback VP already exists from create_client; update it
    vp = db_session.query(VoiceProfile).filter(VoiceProfile.client_id == c.id).first()
    assert vp is not None  # fallback was auto-created
    vp.profile_data = {"base_voice": {}}
    vp.overall_confidence_pct = 78
    vp.sample_count = 5
    db_session.flush()

    resp = client.get("/api/clients")
    data = resp.json()
    assert data[0]["voiceMatchPct"] == 78


# -- POST /api/clients (create) -------------------------------------------


def test_create_client(client):
    """POST /api/clients creates a client and returns correct shape."""
    resp = client.post("/api/clients", json={"name": "New Cafe", "industry": "Food"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "New Cafe"
    assert "id" in data
    assert "status" in data
    assert data["postCount"] == 0
    assert data["sparkline"] == [0, 0, 0, 0, 0, 0]


def test_create_client_duplicate(client):
    """POST /api/clients with duplicate name returns 409."""
    client.post("/api/clients", json={"name": "Dupe Biz", "industry": "Retail"})
    resp = client.post("/api/clients", json={"name": "Dupe Biz", "industry": "Retail"})
    assert resp.status_code == 409


# -- PATCH /api/clients/{client_id} (update) -------------------------------


def test_update_client(client):
    """PATCH /api/clients/{id} updates fields and returns updated shape."""
    create_resp = client.post(
        "/api/clients", json={"name": "Patch Target", "industry": "Tech"}
    )
    client_id = create_resp.json()["id"]

    resp = client.patch(
        f"/api/clients/{client_id}",
        json={"business_description": "We do tech things"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == client_id
    assert data["name"] == "Patch Target"


def test_update_client_not_found(client):
    """PATCH /api/clients/{id} with non-existent ID returns 404."""
    resp = client.patch(
        "/api/clients/99999",
        json={"business_description": "Ghost client"},
    )
    assert resp.status_code == 404


def test_update_recomputes_completeness(client):
    """PATCH with business_description increases profile_completeness_pct and may change status."""
    create_resp = client.post(
        "/api/clients", json={"name": "Growing Biz", "industry": "Consulting"}
    )
    initial = create_resp.json()
    client_id = initial["id"]
    initial_status = initial["status"]
    assert initial_status == "attention"  # fresh client has low completeness

    # Add several fields to push completeness up
    client.patch(
        f"/api/clients/{client_id}",
        json={
            "business_description": "Full-service consulting firm",
            "geography_area": "Toronto, ON",
            "geography_radius_km": 50,
            "industry_vertical": "Management Consulting",
            "target_audience": {"primary": "SMBs"},
            "content_pillars": ["thought leadership", "case studies"],
        },
    )

    # Fetch via GET to see recomputed status
    resp = client.get("/api/clients")
    updated = [c for c in resp.json() if c["id"] == client_id][0]
    # With many fields filled, status should have improved from 'attention'
    assert updated["status"] in ("calibrating", "cruising")


# -- POST /api/clients/{client_id}/archive ---------------------------------


def test_archive_client(client):
    """POST /api/clients/{id}/archive archives the client."""
    create_resp = client.post(
        "/api/clients", json={"name": "To Archive", "industry": "Retail"}
    )
    client_id = create_resp.json()["id"]

    resp = client.post(f"/api/clients/{client_id}/archive")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "To Archive"
    assert "icp_knowledge_retained" in data

    # Client should no longer appear in list (archived)
    list_resp = client.get("/api/clients")
    ids = [c["id"] for c in list_resp.json()]
    assert client_id not in ids


def test_archive_client_not_found(client):
    """POST /api/clients/{id}/archive with non-existent ID returns 404."""
    resp = client.post("/api/clients/99999/archive")
    assert resp.status_code == 404


# -- POST /api/clients/{client_id}/voice/materials ----------------------------


def test_add_voice_material(client, db_session):
    """POST voice material returns id, client_id, source_type, content_length."""
    c = ClientService.create_client(
        db_session, ClientCreate(name="Voice Test Co", industry="Music")
    )
    resp = client.post(
        f"/api/clients/{c.id}/voice/materials",
        json={
            "source_type": "operator_description",
            "content": "We are a friendly, approachable brand.",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["client_id"] == c.id
    assert data["source_type"] == "operator_description"
    assert data["content_length"] == len("We are a friendly, approachable brand.")
    assert "id" in data


def test_add_voice_material_invalid_source_type(client, db_session):
    """POST voice material with invalid source_type returns 422."""
    c = ClientService.create_client(
        db_session, ClientCreate(name="Invalid Voice Co", industry="Tech")
    )
    resp = client.post(
        f"/api/clients/{c.id}/voice/materials",
        json={"source_type": "invalid_type", "content": "Some text"},
    )
    assert resp.status_code == 422


def test_add_voice_material_client_not_found(client):
    """POST voice material for non-existent client returns 404."""
    resp = client.post(
        "/api/clients/99999/voice/materials",
        json={"source_type": "social_post", "content": "Hello world"},
    )
    assert resp.status_code == 404


# -- POST /api/clients/{client_id}/intelligence --------------------------------

from unittest.mock import AsyncMock, patch


def test_add_intelligence_entry(client, db_session):
    """POST intelligence entry returns id, client_id, domain, fact, confidence."""
    c = ClientService.create_client(
        db_session, ClientCreate(name="Intel Test Co", industry="Consulting")
    )
    with patch("sophia.semantic.sync.sync_to_lance", new_callable=AsyncMock):
        resp = client.post(
            f"/api/clients/{c.id}/intelligence",
            json={
                "domain": "business",
                "fact": "Open since 2019",
                "source": "operator:explicit",
                "confidence": 0.8,
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["client_id"] == c.id
    assert data["domain"] == "business"
    assert data["fact"] == "Open since 2019"
    assert data["confidence"] == 0.8
    assert "id" in data


def test_add_intelligence_entry_client_not_found(client):
    """POST intelligence entry for non-existent client returns 404."""
    resp = client.post(
        "/api/clients/99999/intelligence",
        json={"domain": "business", "fact": "Some fact"},
    )
    assert resp.status_code == 404
