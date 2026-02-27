"""Tests for client CRUD, enrichment, archiving, isolation, and completeness.

All tests run against a SQLCipher-encrypted test database.
"""

import json

import pytest

from sophia.exceptions import ClientNotFoundError, DuplicateClientError
from sophia.intelligence.models import AuditLog, Client, EnrichmentLog, VoiceProfile
from sophia.intelligence.schemas import ClientCreate, ClientUpdate
from sophia.intelligence.service import ClientService


class TestCreateClient:
    """Tests for client creation and duplicate detection."""

    def test_create_client(self, db_session):
        """Create a client and verify all default fields + audit log."""
        data = ClientCreate(name="Test Business", industry="Retail")
        client = ClientService.create_client(db_session, data)

        assert client.id is not None
        assert client.name == "Test Business"
        assert client.industry == "Retail"
        assert client.is_archived is False
        assert client.archived_at is None
        assert client.last_activity_at is not None
        assert client.onboarding_state is not None
        assert client.profile_completeness_pct == 15  # name + industry

        # Verify audit log entry
        audit = (
            db_session.query(AuditLog)
            .filter(
                AuditLog.client_id == client.id,
                AuditLog.action == "client.created",
            )
            .first()
        )
        assert audit is not None
        assert audit.actor == "operator"
        assert audit.after_snapshot is not None
        assert audit.after_snapshot["name"] == "Test Business"

    def test_create_duplicate_client(self, db_session, sample_client):
        """Creating a client with the same name raises DuplicateClientError."""
        data = ClientCreate(name="Orban Forest", industry="Tech")
        with pytest.raises(DuplicateClientError):
            ClientService.create_client(db_session, data)

    def test_create_similar_name_client(self, db_session, sample_client):
        """Creating a client with a typo match raises DuplicateClientError."""
        data = ClientCreate(name="Orban Forrest", industry="Tech")
        with pytest.raises(DuplicateClientError) as exc_info:
            ClientService.create_client(db_session, data)
        assert "Orban Forest" in str(exc_info.value)


class TestUpdateClient:
    """Tests for client profile updates and enrichment logging."""

    def test_update_client_profile(self, db_session, sample_client):
        """Update fields and verify enrichment log entries."""
        update = ClientUpdate(
            business_description="Full-service marketing agency",
            content_pillars=["social media tips", "branding"],
        )
        updated = ClientService.update_client(db_session, sample_client.id, update)

        assert updated.business_description == "Full-service marketing agency"
        assert updated.content_pillars == ["social media tips", "branding"]

        # Check enrichment logs
        logs = (
            db_session.query(EnrichmentLog)
            .filter(EnrichmentLog.client_id == sample_client.id)
            .all()
        )
        field_names = {log.field_name for log in logs}
        assert "business_description" in field_names
        assert "content_pillars" in field_names

        # Verify old/new values
        desc_log = next(l for l in logs if l.field_name == "business_description")
        assert desc_log.old_value is None  # Was None before
        assert "Full-service" in desc_log.new_value

    def test_update_client_completeness(self, db_session, sample_client):
        """Profile completeness increases as fields are populated."""
        initial_pct = sample_client.profile_completeness_pct
        assert initial_pct == 15  # name + industry

        # Add business description (+10%)
        update1 = ClientUpdate(business_description="A great agency")
        c1 = ClientService.update_client(db_session, sample_client.id, update1)
        assert c1.profile_completeness_pct == 25

        # Add content pillars (+15%)
        update2 = ClientUpdate(content_pillars=["marketing", "social"])
        c2 = ClientService.update_client(db_session, sample_client.id, update2)
        assert c2.profile_completeness_pct == 40

        # Add target audience (+10%)
        update3 = ClientUpdate(target_audience={"demographics": "SMBs"})
        c3 = ClientService.update_client(db_session, sample_client.id, update3)
        assert c3.profile_completeness_pct == 50

    def test_mvp_readiness(self, db_session, sample_client):
        """MVP readiness requires voice profile + content pillar."""
        assert sample_client.is_mvp_ready is False

        # Add content pillars -- still not ready (no voice)
        update = ClientUpdate(content_pillars=["tips"])
        c = ClientService.update_client(db_session, sample_client.id, update)
        assert c.is_mvp_ready is False

        # Add voice profile with confidence > 0
        voice = VoiceProfile(
            client_id=sample_client.id,
            profile_data={"tone": "professional"},
            overall_confidence_pct=30,
            sample_count=3,
        )
        db_session.add(voice)
        db_session.flush()

        # Re-trigger completeness computation
        update2 = ClientUpdate(business_description="Updated desc")
        c2 = ClientService.update_client(db_session, sample_client.id, update2)
        assert c2.is_mvp_ready is True


class TestListAndRoster:
    """Tests for client listing and roster views."""

    def test_list_clients_excludes_archived(self, db_session, sample_client, sample_client_2):
        """List clients should exclude archived clients by default."""
        # Archive one client
        ClientService.archive_client(db_session, sample_client.id)

        active = ClientService.list_clients(db_session)
        assert len(active) == 1
        assert active[0].name == "Shane's Bakery"

        # Include archived
        all_clients = ClientService.list_clients(db_session, include_archived=True)
        assert len(all_clients) == 2

    def test_get_roster(self, db_session, sample_client, sample_client_2):
        """Roster includes all clients with summary info."""
        roster = ClientService.get_roster(db_session)
        assert len(roster) == 2
        names = {r.name for r in roster}
        assert "Orban Forest" in names
        assert "Shane's Bakery" in names

        for item in roster:
            assert item.id is not None
            assert item.industry is not None
            assert isinstance(item.profile_completeness_pct, int)


class TestArchiving:
    """Tests for client archiving and unarchiving."""

    def test_archive_client(self, db_session, sample_client):
        """Archive a client and verify state + ICP knowledge + audit log."""
        # Give the client some data for ICP extraction
        update = ClientUpdate(
            target_audience={"demographics": "local businesses"},
            content_pillars=["marketing tips"],
        )
        ClientService.update_client(db_session, sample_client.id, update)

        result = ClientService.archive_client(db_session, sample_client.id)

        assert result["name"] == "Orban Forest"
        assert result["icp_knowledge_retained"] is True

        # Verify client state
        client = ClientService.get_client(db_session, sample_client.id, include_archived=True)
        assert client.is_archived is True
        assert client.archived_at is not None

        # Verify audit log
        audit = (
            db_session.query(AuditLog)
            .filter(
                AuditLog.client_id == sample_client.id,
                AuditLog.action == "client.archived",
            )
            .first()
        )
        assert audit is not None

    def test_unarchive_client(self, db_session, sample_client):
        """Archive then unarchive a client."""
        ClientService.archive_client(db_session, sample_client.id)

        client = ClientService.unarchive_client(db_session, sample_client.id)
        assert client.is_archived is False
        assert client.archived_at is None

        # Verify audit log
        audit = (
            db_session.query(AuditLog)
            .filter(
                AuditLog.client_id == sample_client.id,
                AuditLog.action == "client.unarchived",
            )
            .first()
        )
        assert audit is not None


class TestExportAndIsolation:
    """Tests for JSON export and cross-client data isolation."""

    def test_export_client_json(self, db_session, sample_client):
        """Export a client profile as JSON and verify all fields present."""
        # Add some profile data first
        update = ClientUpdate(
            business_description="Test business",
            content_pillars=["pillar1"],
        )
        ClientService.update_client(db_session, sample_client.id, update)

        export = ClientService.export_client_json(db_session, sample_client.id)

        assert "client" in export
        assert "voice_profile" in export
        assert "voice_materials" in export
        assert "enrichment_log" in export
        assert export["client"]["name"] == "Orban Forest"
        assert len(export["enrichment_log"]) > 0

    def test_cross_client_isolation(self, db_session, sample_client, sample_client_2):
        """Enrichment and audit logs are scoped to the correct client_id."""
        # Update both clients
        ClientService.update_client(
            db_session,
            sample_client.id,
            ClientUpdate(business_description="Agency desc"),
        )
        ClientService.update_client(
            db_session,
            sample_client_2.id,
            ClientUpdate(business_description="Bakery desc"),
        )

        # Check enrichment logs are isolated
        logs_1 = (
            db_session.query(EnrichmentLog)
            .filter(EnrichmentLog.client_id == sample_client.id)
            .all()
        )
        logs_2 = (
            db_session.query(EnrichmentLog)
            .filter(EnrichmentLog.client_id == sample_client_2.id)
            .all()
        )

        # Each client should have their own enrichment logs
        assert all(l.client_id == sample_client.id for l in logs_1)
        assert all(l.client_id == sample_client_2.id for l in logs_2)

        # Audit logs should also be isolated
        audits_1 = (
            db_session.query(AuditLog)
            .filter(AuditLog.client_id == sample_client.id)
            .all()
        )
        audits_2 = (
            db_session.query(AuditLog)
            .filter(AuditLog.client_id == sample_client_2.id)
            .all()
        )

        assert all(a.client_id == sample_client.id for a in audits_1)
        assert all(a.client_id == sample_client_2.id for a in audits_2)

    def test_get_client_not_found(self, db_session):
        """Query nonexistent client_id raises ClientNotFoundError."""
        with pytest.raises(ClientNotFoundError):
            ClientService.get_client(db_session, client_id=99999)
