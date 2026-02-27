"""Client service: CRUD, enrichment, archiving, roster, profile completeness.

All methods take a Session as first argument (dependency injection).
Every mutation creates EnrichmentLog and AuditLog entries.
All queries that touch client data include client_id filter (SAFE-01).
"""

import json
from datetime import datetime, timezone
from typing import Optional

from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from sophia.exceptions import ClientNotFoundError, DuplicateClientError
from sophia.intelligence.models import AuditLog, Client, EnrichmentLog, VoiceProfile
from sophia.intelligence.schemas import ClientCreate, ClientRosterItem, ClientUpdate


def _client_snapshot(client: Client) -> dict:
    """Create a JSON-serializable snapshot of a client for audit logging."""
    return {
        "id": client.id,
        "name": client.name,
        "industry": client.industry,
        "business_description": client.business_description,
        "geography_area": client.geography_area,
        "geography_radius_km": client.geography_radius_km,
        "industry_vertical": client.industry_vertical,
        "target_audience": client.target_audience,
        "content_pillars": client.content_pillars,
        "posting_cadence": client.posting_cadence,
        "platform_accounts": client.platform_accounts,
        "guardrails": client.guardrails,
        "brand_assets": client.brand_assets,
        "competitors": client.competitors,
        "market_scope": client.market_scope,
        "is_archived": client.is_archived,
        "profile_completeness_pct": client.profile_completeness_pct,
        "is_mvp_ready": client.is_mvp_ready,
        "onboarding_state": client.onboarding_state,
    }


class ClientService:
    """Client CRUD, enrichment, archiving, roster, and profile completeness."""

    # -- CRUD ----------------------------------------------------------------

    @staticmethod
    def create_client(db: Session, data: ClientCreate) -> Client:
        """Create a new client after duplicate check.

        Uses rapidfuzz WRatio for fuzzy name matching (threshold 90).
        Creates AuditLog entry on success.
        """
        from sophia.intelligence.onboarding import OnboardingService

        # Duplicate detection -- exact + fuzzy
        existing_clients = db.query(Client.name).all()
        for (existing_name,) in existing_clients:
            score = fuzz.WRatio(data.name.lower(), existing_name.lower())
            if score >= 90:
                raise DuplicateClientError(
                    message=f"A client with a similar name already exists: '{existing_name}'",
                    detail=f"Fuzzy match score {score:.0f}% between '{data.name}' and '{existing_name}'",
                    suggestion="Use a different name or update the existing client",
                )

        now = datetime.now(timezone.utc)

        client = Client(
            name=data.name,
            industry=data.industry,
            last_activity_at=now,
        )

        # Initialize onboarding state
        client.onboarding_state = OnboardingService.initialize_onboarding(client)

        # Compute initial profile completeness
        pct, mvp_ready = ClientService.compute_profile_completeness(client)
        client.profile_completeness_pct = pct
        client.is_mvp_ready = mvp_ready

        db.add(client)
        db.flush()  # Get the ID assigned

        # Audit log
        audit = AuditLog(
            client_id=client.id,
            action="client.created",
            actor="operator",
            after_snapshot=_client_snapshot(client),
        )
        db.add(audit)
        db.commit()
        db.refresh(client)

        return client

    @staticmethod
    def get_client(
        db: Session, client_id: int, include_archived: bool = False
    ) -> Client:
        """Get a client by ID. Raises ClientNotFoundError if not found.

        Filters out archived clients unless include_archived=True.
        """
        query = db.query(Client).filter(Client.id == client_id)
        if not include_archived:
            query = query.filter(Client.is_archived == False)  # noqa: E712
        client = query.first()
        if not client:
            raise ClientNotFoundError(
                message=f"Client with id {client_id} not found",
                detail=f"client_id={client_id}, include_archived={include_archived}",
            )
        return client

    @staticmethod
    def get_client_by_name(db: Session, name: str) -> Client:
        """Get a client by name. Tries exact match first, then fuzzy (threshold 80)."""
        # Exact match
        client = db.query(Client).filter(Client.name == name).first()
        if client:
            return client

        # Fuzzy match
        all_clients = db.query(Client).filter(Client.is_archived == False).all()  # noqa: E712
        best_match: Optional[Client] = None
        best_score = 0.0
        for c in all_clients:
            score = fuzz.WRatio(name.lower(), c.name.lower())
            if score > best_score:
                best_score = score
                best_match = c

        if best_match and best_score >= 80:
            return best_match

        raise ClientNotFoundError(
            message=f"No client found matching '{name}'",
            detail=f"Best fuzzy match score: {best_score:.0f}%",
            suggestion="Check client name spelling or use roster view",
        )

    @staticmethod
    def update_client(
        db: Session,
        client_id: int,
        data: ClientUpdate,
        source: str = "operator",
    ) -> Client:
        """Update a client profile. Logs every changed field to EnrichmentLog.

        Recomputes profile completeness after update. Creates AuditLog entry.
        """
        client = ClientService.get_client(db, client_id)
        before = _client_snapshot(client)

        # Apply only non-None fields from update data
        update_fields = data.model_dump(exclude_unset=True)
        for field_name, new_value in update_fields.items():
            old_value = getattr(client, field_name)

            # Skip if value hasn't actually changed
            if old_value == new_value:
                continue

            setattr(client, field_name, new_value)

            # Enrichment log for each changed field
            enrichment = EnrichmentLog(
                client_id=client_id,
                field_name=field_name,
                old_value=json.dumps(old_value, default=str) if old_value is not None else None,
                new_value=json.dumps(new_value, default=str),
                source=source,
            )
            db.add(enrichment)

        # Recompute profile completeness
        pct, mvp_ready = ClientService.compute_profile_completeness(client, db=db)
        client.profile_completeness_pct = pct
        client.is_mvp_ready = mvp_ready

        # Update activity timestamp
        client.last_activity_at = datetime.now(timezone.utc)

        # Audit log
        after = _client_snapshot(client)
        audit = AuditLog(
            client_id=client_id,
            action="profile.updated",
            actor="operator",
            before_snapshot=before,
            after_snapshot=after,
        )
        db.add(audit)
        db.commit()
        db.refresh(client)

        return client

    @staticmethod
    def list_clients(
        db: Session, include_archived: bool = False
    ) -> list[Client]:
        """List all clients, ordered by last_activity_at descending.

        Filters out archived clients unless include_archived=True.
        """
        query = db.query(Client)
        if not include_archived:
            query = query.filter(Client.is_archived == False)  # noqa: E712
        return query.order_by(Client.last_activity_at.desc()).all()

    @staticmethod
    def get_roster(db: Session) -> list[ClientRosterItem]:
        """Return lightweight roster view including archived clients."""
        clients = db.query(Client).order_by(Client.last_activity_at.desc()).all()
        return [
            ClientRosterItem(
                id=c.id,
                name=c.name,
                industry=c.industry,
                profile_completeness_pct=c.profile_completeness_pct,
                is_mvp_ready=c.is_mvp_ready,
                is_archived=c.is_archived,
                last_activity_at=c.last_activity_at,
            )
            for c in clients
        ]

    # -- Profile Completeness ------------------------------------------------

    @staticmethod
    def compute_profile_completeness(
        client: Client, db: Session | None = None
    ) -> tuple[int, bool]:
        """Compute (percentage, is_mvp_ready) from weighted field presence.

        Weights:
          name + industry:          15% (always present after create)
          business_description:     10%
          geography + market_scope: 10%
          content_pillars (>=1):    15%
          posting_cadence:          10%
          target_audience:          10%
          voice profile (>0 conf):  15%
          guardrails:                5%
          platform_accounts:         5%
          brand_assets:              5%

        MVP ready = name + industry + voice_profile exists + at least 1 content pillar.
        """
        pct = 0

        # name + industry (always present after create)
        if client.name and client.industry:
            pct += 15

        # business_description
        if client.business_description:
            pct += 10

        # geography + market_scope
        has_geo = bool(client.geography_area or client.geography_radius_km)
        has_market = bool(client.market_scope)
        if has_geo or has_market:
            pct += 10

        # content_pillars (at least 1)
        has_pillars = bool(client.content_pillars and len(client.content_pillars) >= 1)
        if has_pillars:
            pct += 15

        # posting_cadence
        if client.posting_cadence:
            pct += 10

        # target_audience
        if client.target_audience:
            pct += 10

        # voice profile with confidence > 0
        has_voice = False
        if db is not None:
            voice = (
                db.query(VoiceProfile)
                .filter(VoiceProfile.client_id == client.id)
                .first()
            )
            has_voice = voice is not None and voice.overall_confidence_pct > 0
        elif client.voice_profile is not None:
            has_voice = client.voice_profile.overall_confidence_pct > 0

        if has_voice:
            pct += 15

        # guardrails
        if client.guardrails:
            pct += 5

        # platform_accounts
        if client.platform_accounts:
            pct += 5

        # brand_assets
        if client.brand_assets:
            pct += 5

        # MVP ready check
        mvp_ready = bool(
            client.name
            and client.industry
            and has_voice
            and has_pillars
        )

        return pct, mvp_ready

    # -- Archiving -----------------------------------------------------------

    @staticmethod
    def archive_client(db: Session, client_id: int) -> dict:
        """Archive a client and extract ICP knowledge.

        Sets is_archived=True, extracts institutional knowledge, logs audit.
        """
        from sophia.institutional.service import InstitutionalService

        client = ClientService.get_client(db, client_id)
        before = _client_snapshot(client)

        now = datetime.now(timezone.utc)
        client.is_archived = True
        client.archived_at = now

        # Extract ICP knowledge
        icp_retained = InstitutionalService.extract_from_client(db, client)

        # Audit log
        audit = AuditLog(
            client_id=client_id,
            action="client.archived",
            actor="operator",
            before_snapshot=before,
            after_snapshot=_client_snapshot(client),
        )
        db.add(audit)
        db.commit()

        return {
            "name": client.name,
            "posts_count": 0,  # Populated in later phases
            "active_since": client.created_at.isoformat() if client.created_at else None,
            "icp_knowledge_retained": icp_retained,
        }

    @staticmethod
    def unarchive_client(db: Session, client_id: int) -> Client:
        """Unarchive a client. Sets is_archived=False, archived_at=None."""
        client = ClientService.get_client(db, client_id, include_archived=True)
        before = _client_snapshot(client)

        client.is_archived = False
        client.archived_at = None

        # Audit log
        audit = AuditLog(
            client_id=client_id,
            action="client.unarchived",
            actor="operator",
            before_snapshot=before,
            after_snapshot=_client_snapshot(client),
        )
        db.add(audit)
        db.commit()
        db.refresh(client)

        return client

    # -- JSON Export ---------------------------------------------------------

    @staticmethod
    def export_client_json(db: Session, client_id: int) -> dict:
        """Export full client profile + voice + enrichment as JSON dict.

        For backup, migration, or offboarding.
        """
        client = ClientService.get_client(db, client_id, include_archived=True)

        # Voice profile
        voice = (
            db.query(VoiceProfile)
            .filter(VoiceProfile.client_id == client_id)
            .first()
        )

        # Voice materials
        from sophia.intelligence.models import VoiceMaterial

        materials = (
            db.query(VoiceMaterial)
            .filter(VoiceMaterial.client_id == client_id)
            .all()
        )

        # Enrichment log
        enrichments = (
            db.query(EnrichmentLog)
            .filter(EnrichmentLog.client_id == client_id)
            .all()
        )

        return {
            "client": _client_snapshot(client),
            "voice_profile": {
                "profile_data": voice.profile_data,
                "overall_confidence_pct": voice.overall_confidence_pct,
                "sample_count": voice.sample_count,
                "last_calibrated_at": (
                    voice.last_calibrated_at.isoformat()
                    if voice.last_calibrated_at
                    else None
                ),
            }
            if voice
            else None,
            "voice_materials": [
                {
                    "source_type": m.source_type,
                    "content": m.content,
                    "source_url": m.source_url,
                    "metadata": m.metadata_,
                }
                for m in materials
            ],
            "enrichment_log": [
                {
                    "field_name": e.field_name,
                    "old_value": e.old_value,
                    "new_value": e.new_value,
                    "source": e.source,
                    "reason": e.reason,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in enrichments
            ],
        }
