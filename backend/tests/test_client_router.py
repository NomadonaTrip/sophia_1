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
from sophia.intelligence.schemas import ClientCreate
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
    assert item["voiceMatchPct"] == 0
    assert item["sparkline"] == [0, 0, 0, 0, 0, 0]


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
    vp = VoiceProfile(
        client_id=c.id,
        profile_data={"base_voice": {}},
        overall_confidence_pct=78,
        sample_count=5,
    )
    db_session.add(vp)
    db_session.flush()

    resp = client.get("/api/clients")
    data = resp.json()
    assert data[0]["voiceMatchPct"] == 78
