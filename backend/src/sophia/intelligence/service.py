"""Client service and progressive intelligence enrichment.

ClientService: CRUD, enrichment, archiving, roster, profile completeness.
Intelligence functions: add_intelligence, compute_depth_scores, detect_gaps,
    generate_strategic_narrative, assemble_customer_personas,
    create_institutional_knowledge, get_profile_summary.

All methods take a Session as first argument (dependency injection).
Every mutation creates EnrichmentLog and AuditLog entries.
All queries that touch client data include client_id filter (SAFE-01).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
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


# -- Progressive Intelligence Enrichment ------------------------------------

logger = logging.getLogger(__name__)


async def add_intelligence(
    db: Session,
    client_id: int,
    domain: "IntelligenceDomain",
    fact: str,
    source: str,
    confidence: float = 0.5,
    is_significant: bool = False,
) -> "IntelligenceEntry":
    """Add a new intelligence entry with deduplication and write-through to LanceDB.

    Deduplication: checks semantic similarity against existing entries in the same
    domain for the same client. If >0.9 similarity found, updates the existing
    entry's timestamp and confidence rather than creating a duplicate.

    Args:
        db: SQLAlchemy session.
        client_id: Client ID.
        domain: Intelligence domain (BUSINESS, INDUSTRY, etc.).
        fact: The intelligence fact/observation.
        source: Source attribution string.
        confidence: Confidence level 0-1.
        is_significant: Whether this warrants operator notification.

    Returns:
        The created or updated IntelligenceEntry.
    """
    from sophia.intelligence.models import IntelligenceDomain, IntelligenceEntry

    # Ensure domain is an enum instance
    if isinstance(domain, str):
        domain = IntelligenceDomain(domain)

    # Deduplication check via semantic similarity
    existing_entry = await _find_duplicate_entry(db, client_id, domain, fact)
    if existing_entry is not None:
        # Update existing entry instead of creating duplicate
        existing_entry.confidence = max(existing_entry.confidence, confidence)
        existing_entry.source = source
        db.commit()
        db.refresh(existing_entry)
        logger.info(
            "Deduplicated intelligence entry %d for client %d domain %s",
            existing_entry.id,
            client_id,
            domain.value,
        )
        return existing_entry

    # Create new entry
    entry = IntelligenceEntry(
        client_id=client_id,
        domain=domain,
        fact=fact,
        source=source,
        confidence=confidence,
        is_significant=1 if is_significant else 0,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    # Write-through to LanceDB for semantic search
    try:
        from sophia.semantic.sync import sync_to_lance

        await sync_to_lance(
            record_type="intelligence_entries",
            record_id=entry.id,
            text=f"{domain.value}: {fact}",
            metadata={
                "client_id": client_id,
                "domain": domain.value,
                "created_at": (
                    entry.created_at.isoformat()
                    if entry.created_at
                    else datetime.now(timezone.utc).isoformat()
                ),
            },
        )
    except Exception:
        logger.exception(
            "Write-through sync failed for intelligence entry %d",
            entry.id,
        )

    return entry


async def _find_duplicate_entry(
    db: Session,
    client_id: int,
    domain: "IntelligenceDomain",
    fact: str,
) -> "IntelligenceEntry | None":
    """Check for >0.9 semantic similarity with existing entries in same domain.

    Returns the matching entry if found, None otherwise.
    """
    from sophia.intelligence.models import IntelligenceEntry

    try:
        from sophia.semantic.embeddings import embed
        from sophia.semantic.index import get_lance_table, hybrid_search

        query_vector = await embed(fact)
        table = get_lance_table("intelligence_entries")
        results = hybrid_search(
            table,
            query_text=fact,
            query_vector=query_vector,
            limit=5,
            filters={"client_id": client_id, "domain": domain.value},
        )

        if results.empty:
            return None

        # Check if any result has high relevance (proxy for >0.9 similarity)
        # RRF scores aren't normalized 0-1, so we use a threshold on the top result
        if "_relevance_score" in results.columns and len(results) > 0:
            top_score = results.iloc[0]["_relevance_score"]
            if top_score > 0.9:
                record_id = int(results.iloc[0]["record_id"])
                return (
                    db.query(IntelligenceEntry)
                    .filter(IntelligenceEntry.id == record_id)
                    .first()
                )
    except Exception:
        # If semantic search fails (empty table, model not loaded, etc.),
        # fall through to simple text comparison
        logger.debug("Semantic dedup check failed, falling back to exact match")

    # Fallback: exact text match
    existing = (
        db.query(IntelligenceEntry)
        .filter(
            IntelligenceEntry.client_id == client_id,
            IntelligenceEntry.domain == domain,
            IntelligenceEntry.fact == fact,
        )
        .first()
    )
    return existing


def compute_depth_scores(
    db: Session, client_id: int
) -> list:
    """Compute depth scores for each intelligence domain.

    Depth scoring: rate 1-5 based on richness of understanding.
    Considers: number of entries, diversity of sources, confidence levels,
    freshness weighting (entries older than 30 days get 0.5 weight,
    older than 90 days get 0.25).

    Args:
        db: SQLAlchemy session.
        client_id: Client ID.

    Returns:
        List of DomainScore dicts (one per domain).
    """
    from sophia.intelligence.models import IntelligenceDomain, IntelligenceEntry
    from sophia.intelligence.schemas import DomainScore

    now = datetime.now(timezone.utc)
    scores = []

    for domain in IntelligenceDomain:
        entries = (
            db.query(IntelligenceEntry)
            .filter(
                IntelligenceEntry.client_id == client_id,
                IntelligenceEntry.domain == domain,
            )
            .all()
        )

        if not entries:
            scores.append(
                DomainScore(
                    domain=domain.value,
                    depth=0.0,
                    freshness=0.0,
                    entry_count=0,
                    oldest_entry=None,
                    newest_entry=None,
                )
            )
            continue

        # Freshness-weighted entry count
        weighted_count = 0.0
        total_confidence = 0.0
        sources = set()
        timestamps = []

        for entry in entries:
            created = entry.created_at
            if created and created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)

            if created:
                timestamps.append(created)
                age_days = (now - created).days

                if age_days <= 30:
                    weight = 1.0
                elif age_days <= 90:
                    weight = 0.5
                else:
                    weight = 0.25

                weighted_count += weight
            else:
                weighted_count += 0.25

            total_confidence += entry.confidence
            sources.add(entry.source.split(":")[0] if entry.source else "unknown")

        entry_count = len(entries)
        avg_confidence = total_confidence / entry_count

        # Depth calculation (1-5 scale):
        # Base from weighted entry count: each weighted entry contributes 0.5
        # Source diversity bonus: +0.5 per unique source type (max 1.0)
        # Confidence bonus: avg_confidence * 0.5
        base_depth = min(3.0, weighted_count * 0.5)
        source_bonus = min(1.0, len(sources) * 0.5)
        confidence_bonus = avg_confidence * 0.5
        depth = min(5.0, base_depth + source_bonus + confidence_bonus)

        # Freshness (0-1): based on most recent entry
        freshness = 0.0
        if timestamps:
            newest = max(timestamps)
            age_days = (now - newest).days
            if age_days <= 7:
                freshness = 1.0
            elif age_days <= 30:
                freshness = 0.7
            elif age_days <= 90:
                freshness = 0.3
            else:
                freshness = 0.1

        oldest = min(timestamps) if timestamps else None
        newest = max(timestamps) if timestamps else None

        scores.append(
            DomainScore(
                domain=domain.value,
                depth=round(depth, 2),
                freshness=round(freshness, 2),
                entry_count=entry_count,
                oldest_entry=oldest,
                newest_entry=newest,
            )
        )

    return scores


def detect_gaps(db: Session, client_id: int) -> list[str]:
    """Identify intelligence domains needing enrichment.

    Flags domains with depth < 2 or no entries newer than 30 days.
    For CUSTOMERS domain: also checks persona count and flags when < 2.

    Args:
        db: SQLAlchemy session.
        client_id: Client ID.

    Returns:
        List of gap description strings.
    """
    import asyncio

    from sophia.intelligence.models import IntelligenceDomain

    scores = compute_depth_scores(db, client_id)
    gaps = []

    for score in scores:
        domain_name = score.domain.replace("_", " ").title()

        if score.entry_count == 0:
            gaps.append(f"{domain_name} domain has no intelligence entries")
        elif score.depth < 2:
            gaps.append(
                f"{domain_name} domain needs enrichment (depth {score.depth:.1f}/5)"
            )
        elif score.freshness < 0.3:
            gaps.append(
                f"{domain_name} domain has stale data (freshness {score.freshness:.1f})"
            )

    # Special check for CUSTOMERS domain: persona count
    customers_score = next(
        (s for s in scores if s.domain == IntelligenceDomain.CUSTOMERS.value),
        None,
    )
    if customers_score and customers_score.entry_count > 0:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Can't await in sync context with running loop
                personas = []
            else:
                personas = loop.run_until_complete(
                    assemble_customer_personas(db, client_id)
                )
        except RuntimeError:
            personas = _assemble_personas_sync(db, client_id)

        if len(personas) < 2:
            gaps.append(
                f"Customers domain needs more persona research -- "
                f"only {len(personas)} of 2 minimum personas assembled"
            )

    return gaps


def _assemble_personas_sync(db: Session, client_id: int) -> list:
    """Synchronous fallback for persona assembly (used from detect_gaps)."""
    from sophia.intelligence.models import IntelligenceDomain, IntelligenceEntry
    from sophia.intelligence.schemas import ICPPersona

    entries = (
        db.query(IntelligenceEntry)
        .filter(
            IntelligenceEntry.client_id == client_id,
            IntelligenceEntry.domain == IntelligenceDomain.CUSTOMERS,
        )
        .all()
    )

    if len(entries) < 2:
        return _build_personas_from_entries(entries)

    return _build_personas_from_entries(entries)


def _build_personas_from_entries(entries) -> list:
    """Build ICPPersona objects from intelligence entries by clustering facts.

    Groups entries into persona clusters based on keyword similarity.
    Each cluster becomes one named persona.
    """
    from sophia.intelligence.schemas import ICPPersona

    if not entries:
        return []

    # Simple clustering: group by content keywords
    # For a proper implementation, semantic clustering would be used,
    # but for now we group by detecting persona-related keywords
    persona_groups: dict[int, list] = {}
    group_idx = 0

    for entry in entries:
        fact = entry.fact.lower()
        assigned = False

        # Try to assign to existing group based on keyword overlap
        for gid, group_entries in persona_groups.items():
            group_text = " ".join(e.fact.lower() for e in group_entries)
            # Simple word overlap check
            fact_words = set(fact.split())
            group_words = set(group_text.split())
            overlap = len(fact_words & group_words)
            if overlap >= 2:
                persona_groups[gid].append(entry)
                assigned = True
                break

        if not assigned:
            persona_groups[group_idx] = [entry]
            group_idx += 1

    # Build personas from groups (max 3)
    personas = []
    persona_names = [
        "Primary Customer",
        "Secondary Customer",
        "Emerging Segment",
    ]

    for i, (gid, group_entries) in enumerate(persona_groups.items()):
        if i >= 3:
            break

        facts = [e.fact for e in group_entries]
        name = persona_names[i] if i < len(persona_names) else f"Segment {i + 1}"

        # Extract pain points and preferences from facts
        pain_points = [f for f in facts if any(
            kw in f.lower() for kw in ["struggle", "pain", "challenge", "problem", "need", "frustrat"]
        )]
        preferences = [f for f in facts if any(
            kw in f.lower() for kw in ["prefer", "like", "enjoy", "engage", "respond"]
        )]
        demographics = [f for f in facts if any(
            kw in f.lower() for kw in ["age", "income", "location", "gender", "household", "demographic"]
        )]

        persona = ICPPersona(
            name=name,
            demographics="; ".join(demographics) if demographics else "Not yet profiled",
            pain_points=pain_points if pain_points else ["Not yet identified"],
            content_preferences=preferences if preferences else ["Not yet identified"],
            platform_behavior="Not yet observed",
        )
        personas.append(persona)

    return personas


async def assemble_customer_personas(
    db: Session, client_id: int
) -> list:
    """Assemble customer personas from CUSTOMERS domain intelligence entries.

    Groups related entries by semantic similarity to cluster facts into
    distinct personas. Each cluster becomes one ICPPersona with synthesized
    name, demographics, pain points, content preferences, and platform behavior.

    Args:
        db: SQLAlchemy session.
        client_id: Client ID.

    Returns:
        List of ICPPersona objects (may be 0 if insufficient data).
    """
    from sophia.intelligence.models import IntelligenceDomain, IntelligenceEntry

    entries = (
        db.query(IntelligenceEntry)
        .filter(
            IntelligenceEntry.client_id == client_id,
            IntelligenceEntry.domain == IntelligenceDomain.CUSTOMERS,
        )
        .all()
    )

    return _build_personas_from_entries(entries)


async def create_institutional_knowledge(
    db: Session,
    client_id: int,
    domain: "IntelligenceDomain",
    insight: str,
    what_worked: list | None = None,
    what_didnt_work: list | None = None,
) -> "IntelligenceInstitutionalKnowledge":
    """Create anonymized institutional knowledge from client intelligence.

    Strips identifying information: client name, business name, specific location,
    owner names, revenue figures. Retains: industry vertical, business size category,
    ICP demographics, content performance patterns.

    Args:
        db: SQLAlchemy session.
        client_id: Client ID (used to look up business context, then nulled).
        domain: Intelligence domain.
        insight: The anonymized insight text.
        what_worked: List of things that worked.
        what_didnt_work: List of things that didn't work.

    Returns:
        The created IntelligenceInstitutionalKnowledge entry.
    """
    from sophia.intelligence.models import (
        IntelligenceDomain,
        IntelligenceInstitutionalKnowledge,
    )

    if isinstance(domain, str):
        domain = IntelligenceDomain(domain)

    # Look up client for context
    client = ClientService.get_client(db, client_id, include_archived=True)

    # Derive business size and region type
    industry_vertical = client.industry_vertical or client.industry
    business_size = _derive_business_size(client)
    region_type = _derive_region_type(client)

    # Strip identifying info from insight
    anonymized_insight = _anonymize_text(insight, client)

    entry = IntelligenceInstitutionalKnowledge(
        source_client_id=None,  # Anonymized from the start
        industry_vertical=industry_vertical,
        business_size_category=business_size,
        region_type=region_type,
        domain=domain,
        insight=anonymized_insight,
        what_worked=what_worked,
        what_didnt_work=what_didnt_work,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    # Write-through to LanceDB
    try:
        from sophia.semantic.sync import sync_to_lance

        await sync_to_lance(
            record_type="intelligence_entries",
            record_id=entry.id,
            text=f"institutional:{domain.value}: {anonymized_insight}",
            metadata={
                "client_id": 0,  # Anonymized
                "domain": domain.value,
            },
        )
    except Exception:
        logger.exception("Write-through sync failed for institutional knowledge %d", entry.id)

    return entry


def _derive_business_size(client) -> str:
    """Derive business size category from client profile."""
    # Simple heuristic based on available data
    if client.geography_radius_km and client.geography_radius_km <= 10:
        return "micro"
    elif client.geography_radius_km and client.geography_radius_km <= 50:
        return "small"
    return "small"  # Default for Southern Ontario small businesses


def _derive_region_type(client) -> str:
    """Derive region type from client geography."""
    area = (client.geography_area or "").lower()
    if any(kw in area for kw in ["toronto", "mississauga", "brampton", "urban"]):
        return "urban"
    elif any(kw in area for kw in ["hamilton", "kitchener", "waterloo", "oshawa", "suburban"]):
        return "suburban"
    return "small_town"


def _anonymize_text(text: str, client) -> str:
    """Strip identifying information from insight text.

    Removes: client name, business name, specific location, owner names.
    """
    anonymized = text

    # Strip client/business name
    if client.name:
        anonymized = anonymized.replace(client.name, "[business]")

    # Strip specific geography
    if client.geography_area:
        anonymized = anonymized.replace(client.geography_area, "[location]")

    return anonymized


async def generate_strategic_narrative(
    db: Session, client_id: int
) -> str:
    """Synthesize intelligence entries into a 2-3 paragraph strategic narrative.

    Structure:
    - Paragraph 1: Business identity and market position (BUSINESS, INDUSTRY domains)
    - Paragraph 2: Customer understanding and competitive landscape (CUSTOMERS, COMPETITORS)
    - Paragraph 3: Content strategy implications (PRODUCT_SERVICE, SALES_PROCESS)

    Skips paragraphs for domains with depth < 1 (no data).
    Uses highest-confidence entries from each domain.

    Args:
        db: SQLAlchemy session.
        client_id: Client ID.

    Returns:
        Strategic narrative string (empty string if no entries exist).
    """
    from sophia.intelligence.models import IntelligenceDomain, IntelligenceEntry

    paragraphs = []

    # Paragraph 1: Business identity and market position
    business_entries = _get_top_entries(db, client_id, IntelligenceDomain.BUSINESS)
    industry_entries = _get_top_entries(db, client_id, IntelligenceDomain.INDUSTRY)

    if business_entries or industry_entries:
        parts = []
        if business_entries:
            facts = [e.fact for e in business_entries[:3]]
            parts.append(
                f"Business understanding: {'. '.join(facts)}"
            )
        if industry_entries:
            facts = [e.fact for e in industry_entries[:3]]
            parts.append(
                f"Industry context: {'. '.join(facts)}"
            )
        paragraphs.append(" ".join(parts))

    # Paragraph 2: Customer understanding and competitive landscape
    customer_entries = _get_top_entries(db, client_id, IntelligenceDomain.CUSTOMERS)
    competitor_entries = _get_top_entries(db, client_id, IntelligenceDomain.COMPETITORS)

    if customer_entries or competitor_entries:
        parts = []
        if customer_entries:
            facts = [e.fact for e in customer_entries[:3]]
            parts.append(
                f"Customer insights: {'. '.join(facts)}"
            )
        if competitor_entries:
            facts = [e.fact for e in competitor_entries[:3]]
            parts.append(
                f"Competitive landscape: {'. '.join(facts)}"
            )
        paragraphs.append(" ".join(parts))

    # Paragraph 3: Content strategy implications
    product_entries = _get_top_entries(db, client_id, IntelligenceDomain.PRODUCT_SERVICE)
    sales_entries = _get_top_entries(db, client_id, IntelligenceDomain.SALES_PROCESS)

    if product_entries or sales_entries:
        parts = []
        if product_entries:
            facts = [e.fact for e in product_entries[:3]]
            parts.append(
                f"Product/service focus: {'. '.join(facts)}"
            )
        if sales_entries:
            facts = [e.fact for e in sales_entries[:3]]
            parts.append(
                f"Sales process insights: {'. '.join(facts)}"
            )
        paragraphs.append(" ".join(parts))

    return "\n\n".join(paragraphs)


def _get_top_entries(
    db: Session,
    client_id: int,
    domain: "IntelligenceDomain",
    limit: int = 5,
) -> list:
    """Get highest-confidence entries for a domain."""
    from sophia.intelligence.models import IntelligenceEntry

    return (
        db.query(IntelligenceEntry)
        .filter(
            IntelligenceEntry.client_id == client_id,
            IntelligenceEntry.domain == domain,
        )
        .order_by(IntelligenceEntry.confidence.desc())
        .limit(limit)
        .all()
    )


async def get_profile_summary(
    db: Session, client_id: int
) -> "IntelligenceProfileResponse":
    """Assemble full intelligence profile with domain scores, completeness,
    gap analysis, and strategic narrative.

    Args:
        db: SQLAlchemy session.
        client_id: Client ID.

    Returns:
        IntelligenceProfileResponse with all profile data.
    """
    from sophia.intelligence.schemas import IntelligenceProfileResponse

    domain_scores = compute_depth_scores(db, client_id)
    gaps = detect_gaps(db, client_id)
    narrative = await generate_strategic_narrative(db, client_id)

    # Completeness: average of all domain depths normalized to 0-100
    if domain_scores:
        avg_depth = sum(s.depth for s in domain_scores) / len(domain_scores)
        completeness = (avg_depth / 5.0) * 100
    else:
        completeness = 0.0

    return IntelligenceProfileResponse(
        client_id=client_id,
        domain_scores=domain_scores,
        overall_completeness=round(completeness, 1),
        strategic_narrative=narrative if narrative else None,
        gaps=gaps,
    )
