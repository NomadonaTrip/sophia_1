"""Tiered skill governance: classify, auto-acquire safe, queue risky.

Extends Phase 6's capability discovery registry with risk classification.
Safe capabilities (read-only) are auto-acquired without operator approval.
Risky capabilities (write/publish/spend) require operator approval via
daily briefing queue.

Integration point: The daily cycle's Learn stage calls
process_proposals_with_governance() after process_open_gaps() discovers
and evaluates new capabilities.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sophia.capabilities.models import (
        CapabilityProposal,
        CapabilityRegistry,
        DiscoveredCapability,
    )
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Risk classification keywords
# ---------------------------------------------------------------------------

# Capability types considered inherently safe (read-only operations)
_SAFE_CAPABILITY_TYPES = frozenset({
    "research", "analytics", "read", "search", "monitor", "scrape",
    "fetch", "query",
})

# Verbs in descriptions that indicate read-only behaviour
_SAFE_DESCRIPTION_VERBS = frozenset({
    "list", "get", "search", "read", "fetch", "query", "monitor",
    "analyze",
})

# Capability types considered inherently risky
_RISKY_CAPABILITY_TYPES = frozenset({
    "publisher", "sender", "payment",
})

# Verbs in descriptions that indicate write/publish/spend behaviour
_RISKY_DESCRIPTION_VERBS = frozenset({
    "post", "publish", "send", "delete", "update", "create", "pay",
    "charge", "transfer", "modify", "write",
})


def classify_skill_risk(capability: DiscoveredCapability) -> str:
    """Classify a discovered capability as 'safe' or 'risky'.

    Classification rules (keyword-based):
    - SAFE: capability source is 'mcp_server' with read-only description verbs,
      OR source/description contains safe-type keywords.
    - RISKY: description contains write verbs, OR source/type contains risky
      keywords.
    - Default: 'risky' (conservative -- unknown capabilities require approval).

    Returns:
        'safe' or 'risky'
    """
    description_lower = (capability.description or "").lower()
    source_lower = (capability.source or "").lower()
    # DiscoveredCapability doesn't have capability_type, but the plan
    # references it. We use 'source' plus description for classification.
    # If a capability_type attribute is present (future extension), use it.
    capability_type_lower = getattr(capability, "capability_type", "") or ""
    capability_type_lower = capability_type_lower.lower()

    # Helper: check if any keyword appears as substring in text
    # This handles conjugated forms (e.g. "searches" matches "search")
    def _has_keyword(text: str, keywords: frozenset) -> list[str]:
        return [kw for kw in keywords if kw in text]

    # --- Check RISKY indicators first (risky wins over safe) ---

    # Risky capability type
    risky_type_matches = _has_keyword(capability_type_lower, _RISKY_CAPABILITY_TYPES)
    if risky_type_matches:
        logger.info(
            "Classified '%s' as RISKY (capability_type contains '%s')",
            capability.name, risky_type_matches[0],
        )
        return "risky"

    # Risky description verbs (substring match)
    risky_matches = _has_keyword(description_lower, _RISKY_DESCRIPTION_VERBS)
    if risky_matches:
        logger.info(
            "Classified '%s' as RISKY (description contains: %s)",
            capability.name, ", ".join(sorted(risky_matches)),
        )
        return "risky"

    # --- Check SAFE indicators ---

    # Safe capability type
    safe_type_matches = _has_keyword(capability_type_lower, _SAFE_CAPABILITY_TYPES)
    if safe_type_matches:
        logger.info(
            "Classified '%s' as SAFE (capability_type contains '%s')",
            capability.name, safe_type_matches[0],
        )
        return "safe"

    # MCP server source with read-only description verbs (substring match)
    if source_lower in ("mcp_registry", "mcp_server"):
        safe_matches = _has_keyword(description_lower, _SAFE_DESCRIPTION_VERBS)
        if safe_matches:
            logger.info(
                "Classified '%s' as SAFE (MCP source + description: %s)",
                capability.name, ", ".join(sorted(safe_matches)),
            )
            return "safe"

    # Safe description verbs (non-MCP sources too, if no risky verbs matched)
    safe_matches = _has_keyword(description_lower, _SAFE_DESCRIPTION_VERBS)
    if safe_matches:
        logger.info(
            "Classified '%s' as SAFE (description contains: %s)",
            capability.name, ", ".join(sorted(safe_matches)),
        )
        return "safe"

    # --- Default: risky (conservative) ---
    logger.info(
        "Classified '%s' as RISKY (default -- no clear safe indicators)",
        capability.name,
    )
    return "risky"


def auto_acquire_safe_skill(
    db: Session,
    proposal_id: int,
) -> CapabilityRegistry | None:
    """Auto-acquire a skill if its discovered capability is classified safe.

    If the proposal's discovered capability is classified as 'safe',
    automatically approve it via capabilities.service.approve_proposal()
    and log the auto-acquisition.

    Returns the registry entry if auto-acquired, None if classified as risky
    (caller should use queue_risky_skill instead).
    """
    try:
        from sophia.capabilities.models import CapabilityProposal, DiscoveredCapability
        from sophia.capabilities.service import approve_proposal
    except ImportError:
        logger.error("Cannot import capabilities module -- skill governance unavailable")
        return None

    proposal = db.get(CapabilityProposal, proposal_id)
    if proposal is None:
        logger.warning("Proposal #%d not found", proposal_id)
        return None

    discovered = db.get(DiscoveredCapability, proposal.discovered_id)
    if discovered is None:
        logger.warning(
            "Discovered capability #%d not found for proposal #%d",
            proposal.discovered_id, proposal_id,
        )
        return None

    risk = classify_skill_risk(discovered)

    if risk == "risky":
        logger.info(
            "Proposal #%d classified as risky -- not auto-acquiring",
            proposal_id,
        )
        return None

    # Safe -- auto-approve
    registry_entry = approve_proposal(
        db, proposal_id, review_notes="Auto-acquired: classified as safe skill"
    )
    logger.info(
        "Auto-acquired safe skill: proposal #%d -> registry #%d (%s)",
        proposal_id, registry_entry.id, registry_entry.name,
    )
    return registry_entry


def queue_risky_skill(
    db: Session,
    proposal_id: int,
    reason: str = "",
) -> CapabilityProposal:
    """Queue a risky skill proposal for operator approval in daily briefing.

    Leaves proposal in 'pending' status and adds risk metadata via
    review_notes JSON.

    Returns the updated proposal.
    """
    try:
        from sophia.capabilities.models import CapabilityProposal
    except ImportError:
        raise RuntimeError("Cannot import capabilities module")

    proposal = db.get(CapabilityProposal, proposal_id)
    if proposal is None:
        raise ValueError(f"Proposal #{proposal_id} not found")

    # Add risk tier metadata to review_notes (JSON-encoded)
    metadata = {
        "risk_tier": "risky",
        "queued_reason": reason or "Capability requires operator approval (write/publish/spend)",
    }
    proposal.review_notes = json.dumps(metadata)
    db.flush()

    logger.info(
        "Queued risky skill for approval: proposal #%d (%s)",
        proposal_id,
        reason or "default risky classification",
    )
    return proposal


def process_proposals_with_governance(db: Session) -> dict:
    """Process all pending proposals through governance classification.

    Iterates all pending (non-auto-rejected) proposals, classifies each,
    auto-acquires safe ones, queues risky ones for operator approval.

    Returns:
        {"auto_acquired": N, "queued_for_approval": M}
    """
    try:
        from sophia.capabilities.models import (
            CapabilityProposal,
            DiscoveredCapability,
            ProposalStatus,
        )
    except ImportError:
        logger.error("Cannot import capabilities module")
        return {"auto_acquired": 0, "queued_for_approval": 0}

    # Get all pending, non-auto-rejected proposals
    pending_proposals = (
        db.query(CapabilityProposal)
        .filter(
            CapabilityProposal.status == ProposalStatus.pending.value,
            CapabilityProposal.auto_rejected.is_(False),
        )
        .all()
    )

    auto_acquired = 0
    queued_for_approval = 0

    for proposal in pending_proposals:
        discovered = db.get(DiscoveredCapability, proposal.discovered_id)
        if discovered is None:
            logger.warning(
                "Skipping proposal #%d: discovered capability #%d not found",
                proposal.id, proposal.discovered_id,
            )
            continue

        risk = classify_skill_risk(discovered)

        if risk == "safe":
            result = auto_acquire_safe_skill(db, proposal.id)
            if result is not None:
                auto_acquired += 1
            else:
                # Shouldn't happen -- classify said safe but acquire failed
                logger.warning(
                    "Failed to auto-acquire proposal #%d despite safe classification",
                    proposal.id,
                )
        else:
            queue_risky_skill(db, proposal.id)
            queued_for_approval += 1

    logger.info(
        "Governance processing: %d auto-acquired, %d queued for approval",
        auto_acquired, queued_for_approval,
    )

    return {
        "auto_acquired": auto_acquired,
        "queued_for_approval": queued_for_approval,
    }
