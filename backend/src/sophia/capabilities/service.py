"""Capability discovery service layer.

Orchestrates gap logging, search + evaluation, approval/rejection,
registry management, and batch processing of open gaps.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from sophia.capabilities.evaluation import (
    evaluate_capability,
    score_discovered_capability,
)
from sophia.capabilities.models import (
    CapabilityGap,
    CapabilityProposal,
    CapabilityRegistry,
    CapabilityStatus,
    DiscoveredCapability,
    GapStatus,
    ProposalStatus,
)
from sophia.capabilities.search import (
    DiscoveredCapabilityData,
    search_all_sources,
)

logger = logging.getLogger(__name__)

# -- Duplicate detection threshold (simple keyword overlap) -------------------
_DUPLICATE_SIMILARITY_THRESHOLD = 0.7


def _is_duplicate_gap(existing_description: str, new_description: str) -> bool:
    """Check if two gap descriptions are substantially similar.

    Uses simple word overlap ratio to catch duplicates without
    requiring external NLP libraries.
    """
    existing_words = set(existing_description.lower().split())
    new_words = set(new_description.lower().split())

    if not existing_words or not new_words:
        return False

    intersection = existing_words & new_words
    union = existing_words | new_words
    jaccard = len(intersection) / len(union) if union else 0

    return jaccard >= _DUPLICATE_SIMILARITY_THRESHOLD


# -- Gap management -----------------------------------------------------------


def log_capability_gap(
    db: Session,
    description: str,
    detected_during: str,
    client_id: int | None = None,
) -> CapabilityGap:
    """Log a new capability gap detected during operations.

    Checks for duplicate gaps (similar description text) before creating.
    Returns the existing gap if a duplicate is found.
    """
    # Check for duplicates among open/searching gaps
    existing_gaps = (
        db.query(CapabilityGap)
        .filter(CapabilityGap.status.in_([GapStatus.open.value, GapStatus.searching.value]))
        .all()
    )

    for gap in existing_gaps:
        if _is_duplicate_gap(gap.description, description):
            logger.info(
                "Duplicate gap detected (similar to gap #%d), skipping creation",
                gap.id,
            )
            return gap

    gap = CapabilityGap(
        description=description,
        detected_during=detected_during,
        client_id=client_id,
        status=GapStatus.open.value,
    )
    db.add(gap)
    db.flush()

    logger.info("Logged capability gap #%d: %s", gap.id, description[:80])
    return gap


def get_gap(db: Session, gap_id: int) -> CapabilityGap | None:
    """Get a single capability gap by ID."""
    return db.get(CapabilityGap, gap_id)


def list_gaps(
    db: Session, status: str | None = None
) -> list[CapabilityGap]:
    """List capability gaps, optionally filtered by status."""
    query = db.query(CapabilityGap)
    if status:
        query = query.filter(CapabilityGap.status == status)
    return query.order_by(CapabilityGap.created_at.desc()).all()


# -- Search and evaluate ------------------------------------------------------


async def search_and_evaluate_gap(
    db: Session, gap_id: int
) -> list[CapabilityProposal]:
    """Search for solutions to a gap and create evaluated proposals.

    1. Load gap from DB
    2. Search MCP Registry + GitHub
    3. For each result: persist, score, evaluate, create proposal
    4. Update gap status to proposals_ready
    5. Return proposals sorted by composite score (non-auto-rejected first)
    """
    gap = db.get(CapabilityGap, gap_id)
    if gap is None:
        raise ValueError(f"Gap #{gap_id} not found")

    # Update status to searching
    gap.status = GapStatus.searching.value
    db.flush()

    # Search all sources
    discovered = await search_all_sources(gap.description)

    proposals: list[CapabilityProposal] = []

    for cap_data in discovered:
        # 1. Persist as DiscoveredCapability
        disc = DiscoveredCapability(
            gap_id=gap.id,
            source=cap_data.source,
            name=cap_data.name,
            description=cap_data.description,
            url=cap_data.url,
            version=cap_data.version,
            stars=cap_data.stars,
            last_updated=cap_data.last_updated,
        )
        db.add(disc)
        db.flush()

        # 2. Score using heuristic rubric
        rubric_scores = score_discovered_capability(cap_data, gap.description)

        # 3. Evaluate (auto-reject, composite, recommendation)
        eval_result = evaluate_capability(rubric_scores)

        # 4. Create CapabilityProposal
        justification = {
            s.dimension: s.justification for s in eval_result.scores
        }
        score_map = {s.dimension: s.score for s in eval_result.scores}

        proposal = CapabilityProposal(
            gap_id=gap.id,
            discovered_id=disc.id,
            relevance_score=score_map.get("relevance", 0),
            quality_score=score_map.get("quality", 0),
            security_score=score_map.get("security", 0),
            fit_score=score_map.get("fit", 0),
            composite_score=eval_result.composite_score,
            recommendation=eval_result.recommendation,
            auto_rejected=eval_result.auto_rejected,
            rejection_reason=eval_result.rejection_reason,
            justification_json=json.dumps(justification),
            status=ProposalStatus.pending.value,
        )
        db.add(proposal)
        db.flush()
        proposals.append(proposal)

    # Update gap status
    gap.status = GapStatus.proposals_ready.value
    gap.last_searched_at = datetime.now(timezone.utc)
    db.flush()

    # Sort: non-auto-rejected first, then by composite score descending
    proposals.sort(
        key=lambda p: (p.auto_rejected, -p.composite_score)
    )

    logger.info(
        "Gap #%d: found %d capabilities, created %d proposals (%d auto-rejected)",
        gap.id,
        len(discovered),
        len(proposals),
        sum(1 for p in proposals if p.auto_rejected),
    )

    return proposals


# -- Approval / Rejection -----------------------------------------------------


def approve_proposal(
    db: Session,
    proposal_id: int,
    review_notes: str | None = None,
) -> CapabilityRegistry:
    """Approve a capability proposal and create a registry entry.

    CRITICAL: Sophia never installs without explicit operator approval.
    This is the only path to creating CapabilityRegistry entries.
    """
    proposal = db.get(CapabilityProposal, proposal_id)
    if proposal is None:
        raise ValueError(f"Proposal #{proposal_id} not found")

    if proposal.status != ProposalStatus.pending.value:
        raise ValueError(
            f"Proposal #{proposal_id} has status '{proposal.status}', "
            f"expected 'pending'"
        )

    # Load discovered capability for metadata
    discovered = db.get(DiscoveredCapability, proposal.discovered_id)
    if discovered is None:
        raise ValueError(f"Discovered capability #{proposal.discovered_id} not found")

    # Create registry entry
    registry_entry = CapabilityRegistry(
        name=discovered.name,
        description=discovered.description,
        source=discovered.source,
        source_url=discovered.url,
        version=discovered.version,
        installed_at=datetime.now(timezone.utc),
        status=CapabilityStatus.active.value,
        proposal_id=proposal.id,
        failure_count=0,
        auto_disable_threshold=5,
    )
    db.add(registry_entry)
    db.flush()

    # Update proposal status
    proposal.status = ProposalStatus.approved.value
    proposal.reviewed_at = datetime.now(timezone.utc)
    proposal.review_notes = review_notes

    # Resolve the gap
    gap = db.get(CapabilityGap, proposal.gap_id)
    if gap:
        gap.status = GapStatus.resolved.value
        gap.resolved_by_id = registry_entry.id

    db.flush()

    logger.info(
        "Approved proposal #%d -> registry entry #%d (%s)",
        proposal.id,
        registry_entry.id,
        registry_entry.name,
    )

    return registry_entry


def reject_proposal(
    db: Session,
    proposal_id: int,
    review_notes: str,
) -> CapabilityProposal:
    """Reject a capability proposal with required operator rationale."""
    proposal = db.get(CapabilityProposal, proposal_id)
    if proposal is None:
        raise ValueError(f"Proposal #{proposal_id} not found")

    if proposal.status != ProposalStatus.pending.value:
        raise ValueError(
            f"Proposal #{proposal_id} has status '{proposal.status}', "
            f"expected 'pending'"
        )

    proposal.status = ProposalStatus.rejected.value
    proposal.reviewed_at = datetime.now(timezone.utc)
    proposal.review_notes = review_notes
    db.flush()

    logger.info(
        "Rejected proposal #%d: %s",
        proposal.id,
        review_notes[:80],
    )

    return proposal


# -- Registry management ------------------------------------------------------


def get_registry(
    db: Session, status: str | None = None
) -> list[CapabilityRegistry]:
    """List installed capabilities, optionally filtered by status."""
    query = db.query(CapabilityRegistry)
    if status:
        query = query.filter(CapabilityRegistry.status == status)
    return query.order_by(CapabilityRegistry.installed_at.desc()).all()


def get_registry_entry(
    db: Session, registry_id: int
) -> CapabilityRegistry | None:
    """Get a single registry entry by ID."""
    return db.get(CapabilityRegistry, registry_id)


def record_capability_failure(
    db: Session, registry_id: int
) -> CapabilityRegistry:
    """Record a runtime failure for an installed capability.

    Increments failure_count. If count reaches auto_disable_threshold,
    sets status to 'disabled'.
    """
    entry = db.get(CapabilityRegistry, registry_id)
    if entry is None:
        raise ValueError(f"Registry entry #{registry_id} not found")

    entry.failure_count += 1

    if entry.failure_count >= entry.auto_disable_threshold:
        entry.status = CapabilityStatus.disabled.value
        logger.warning(
            "Auto-disabled capability '%s' (#%d) after %d failures",
            entry.name,
            entry.id,
            entry.failure_count,
        )

    db.flush()
    return entry


# -- Batch processing ---------------------------------------------------------


async def process_open_gaps(db: Session) -> dict:
    """Batch job: search and evaluate all open/stale gaps.

    Called by APScheduler weekly (Sunday 2 AM). Processes:
    - Gaps with status 'open'
    - Gaps with status 'searching' and last_searched_at > 7 days ago

    Returns summary dict with processing stats.
    """
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    gaps = (
        db.query(CapabilityGap)
        .filter(
            (CapabilityGap.status == GapStatus.open.value)
            | (
                (CapabilityGap.status == GapStatus.searching.value)
                & (
                    (CapabilityGap.last_searched_at.is_(None))
                    | (CapabilityGap.last_searched_at < cutoff)
                )
            )
        )
        .all()
    )

    gaps_processed = 0
    proposals_created = 0
    auto_rejected_count = 0

    for gap in gaps:
        try:
            proposals = await search_and_evaluate_gap(db, gap.id)
            gaps_processed += 1
            proposals_created += len(proposals)
            auto_rejected_count += sum(
                1 for p in proposals if p.auto_rejected
            )
        except Exception as e:
            logger.error(
                "Failed to process gap #%d: %s", gap.id, str(e)
            )

    logger.info(
        "Batch gap processing: %d gaps, %d proposals, %d auto-rejected",
        gaps_processed,
        proposals_created,
        auto_rejected_count,
    )

    return {
        "gaps_processed": gaps_processed,
        "proposals_created": proposals_created,
        "auto_rejected_count": auto_rejected_count,
    }


# -- Proposal listing ---------------------------------------------------------


def list_proposals(
    db: Session,
    gap_id: int | None = None,
    status: str | None = None,
) -> list[CapabilityProposal]:
    """List proposals with optional gap_id and status filters."""
    query = db.query(CapabilityProposal)
    if gap_id is not None:
        query = query.filter(CapabilityProposal.gap_id == gap_id)
    if status:
        query = query.filter(CapabilityProposal.status == status)
    return query.order_by(
        CapabilityProposal.auto_rejected.asc(),
        CapabilityProposal.composite_score.desc(),
    ).all()


def get_proposal(
    db: Session, proposal_id: int
) -> CapabilityProposal | None:
    """Get a single proposal by ID."""
    return db.get(CapabilityProposal, proposal_id)
