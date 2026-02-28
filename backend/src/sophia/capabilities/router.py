"""Capability discovery REST API router.

Provides endpoints for gap management, search triggering, proposal
listing, approval/rejection, and registry browsing. DB dependency
uses lazy-import placeholder pattern (wired in main.py).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from sophia.capabilities.models import (
    CapabilityGap,
    CapabilityProposal,
    CapabilityRegistry,
    DiscoveredCapability,
)
from sophia.capabilities.schemas import (
    ApprovalRequest,
    GapCreate,
    GapListResponse,
    GapResponse,
    ProposalListResponse,
    ProposalResponse,
    DiscoveredCapabilityResponse,
    RejectionRequest,
    RegistryEntryResponse,
    RegistryListResponse,
)
from sophia.capabilities.service import (
    approve_proposal,
    get_gap,
    get_proposal,
    get_registry,
    get_registry_entry,
    list_gaps,
    list_proposals,
    log_capability_gap,
    record_capability_failure,
    reject_proposal,
    search_and_evaluate_gap,
)

capabilities_router = APIRouter(
    prefix="/api/capabilities", tags=["capabilities"]
)


# -- DB dependency placeholder ------------------------------------------------


def _get_db():
    """Yield a SQLAlchemy session. Lazy-imports engine to avoid slow NTFS imports at startup."""
    from sophia.db.engine import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -- Helper to build ProposalResponse with nested discovered data ----


def _proposal_to_response(
    proposal: CapabilityProposal, db: Session
) -> ProposalResponse:
    """Convert a CapabilityProposal ORM instance to ProposalResponse with nested discovered data."""
    discovered = db.get(DiscoveredCapability, proposal.discovered_id)
    discovered_resp = None
    if discovered:
        discovered_resp = DiscoveredCapabilityResponse.model_validate(discovered)

    return ProposalResponse(
        id=proposal.id,
        gap_id=proposal.gap_id,
        discovered_id=proposal.discovered_id,
        relevance_score=proposal.relevance_score,
        quality_score=proposal.quality_score,
        security_score=proposal.security_score,
        fit_score=proposal.fit_score,
        composite_score=proposal.composite_score,
        recommendation=proposal.recommendation,
        auto_rejected=proposal.auto_rejected,
        rejection_reason=proposal.rejection_reason,
        justification_json=proposal.justification_json,
        status=proposal.status,
        reviewed_at=proposal.reviewed_at,
        review_notes=proposal.review_notes,
        created_at=proposal.created_at,
        updated_at=proposal.updated_at,
        discovered=discovered_resp,
    )


# -- Gap endpoints ------------------------------------------------------------


@capabilities_router.post("/gaps", response_model=GapResponse, status_code=201)
def create_gap(
    body: GapCreate,
    db: Session = Depends(_get_db),
):
    """Log a new capability gap detected during operations."""
    gap = log_capability_gap(
        db,
        description=body.description,
        detected_during=body.detected_during,
        client_id=body.client_id,
    )
    db.commit()
    db.refresh(gap)
    return gap


@capabilities_router.get("/gaps", response_model=GapListResponse)
def get_gaps(
    status: Optional[str] = Query(None, description="Filter by gap status"),
    db: Session = Depends(_get_db),
):
    """List capability gaps with optional status filter."""
    gaps = list_gaps(db, status=status)
    return GapListResponse(
        items=[GapResponse.model_validate(g) for g in gaps],
        total=len(gaps),
    )


@capabilities_router.get("/gaps/{gap_id}", response_model=GapResponse)
def get_gap_detail(
    gap_id: int,
    db: Session = Depends(_get_db),
):
    """Get details for a specific capability gap."""
    gap = get_gap(db, gap_id)
    if gap is None:
        raise HTTPException(status_code=404, detail=f"Gap #{gap_id} not found")
    return gap


# -- Search endpoints ---------------------------------------------------------


@capabilities_router.post(
    "/gaps/{gap_id}/search",
    response_model=ProposalListResponse,
)
async def trigger_gap_search(
    gap_id: int,
    db: Session = Depends(_get_db),
):
    """Manually trigger search and evaluation for a specific gap."""
    gap = get_gap(db, gap_id)
    if gap is None:
        raise HTTPException(status_code=404, detail=f"Gap #{gap_id} not found")

    proposals = await search_and_evaluate_gap(db, gap_id)
    db.commit()

    items = [_proposal_to_response(p, db) for p in proposals]
    auto_rejected_count = sum(1 for p in proposals if p.auto_rejected)

    return ProposalListResponse(
        items=items,
        total=len(items),
        auto_rejected_count=auto_rejected_count,
    )


# -- Proposal endpoints -------------------------------------------------------


@capabilities_router.get("/proposals", response_model=ProposalListResponse)
def get_proposals(
    gap_id: Optional[int] = Query(None, description="Filter by gap ID"),
    status: Optional[str] = Query(None, description="Filter by proposal status"),
    db: Session = Depends(_get_db),
):
    """List proposals with optional gap_id and status filters."""
    proposals = list_proposals(db, gap_id=gap_id, status=status)
    items = [_proposal_to_response(p, db) for p in proposals]
    auto_rejected_count = sum(1 for p in proposals if p.auto_rejected)

    return ProposalListResponse(
        items=items,
        total=len(items),
        auto_rejected_count=auto_rejected_count,
    )


@capabilities_router.get(
    "/proposals/{proposal_id}", response_model=ProposalResponse
)
def get_proposal_detail(
    proposal_id: int,
    db: Session = Depends(_get_db),
):
    """Get details for a specific proposal including rubric scores."""
    proposal = get_proposal(db, proposal_id)
    if proposal is None:
        raise HTTPException(
            status_code=404, detail=f"Proposal #{proposal_id} not found"
        )
    return _proposal_to_response(proposal, db)


# -- Approval / Rejection endpoints -------------------------------------------


@capabilities_router.post(
    "/proposals/{proposal_id}/approve",
    response_model=RegistryEntryResponse,
    status_code=201,
)
def approve_capability(
    proposal_id: int,
    body: ApprovalRequest,
    db: Session = Depends(_get_db),
):
    """Approve a capability proposal. Creates a registry entry."""
    try:
        registry_entry = approve_proposal(
            db, proposal_id, review_notes=body.review_notes
        )
        db.commit()
        db.refresh(registry_entry)
        return registry_entry
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg:
            raise HTTPException(status_code=404, detail=error_msg)
        # Invalid state transition (e.g., already approved)
        raise HTTPException(status_code=409, detail=error_msg)


@capabilities_router.post(
    "/proposals/{proposal_id}/reject",
    response_model=ProposalResponse,
)
def reject_capability(
    proposal_id: int,
    body: RejectionRequest,
    db: Session = Depends(_get_db),
):
    """Reject a capability proposal. Operator must provide rationale."""
    try:
        proposal = reject_proposal(
            db, proposal_id, review_notes=body.review_notes
        )
        db.commit()
        db.refresh(proposal)
        return _proposal_to_response(proposal, db)
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg:
            raise HTTPException(status_code=404, detail=error_msg)
        raise HTTPException(status_code=409, detail=error_msg)


# -- Registry endpoints -------------------------------------------------------


@capabilities_router.get("/registry", response_model=RegistryListResponse)
def get_capability_registry(
    status: Optional[str] = Query(
        None, description="Filter by capability status"
    ),
    db: Session = Depends(_get_db),
):
    """List all installed capabilities with optional status filter."""
    entries = get_registry(db, status=status)
    active_count = sum(1 for e in entries if e.status == "active")
    disabled_count = sum(1 for e in entries if e.status == "disabled")

    return RegistryListResponse(
        items=[RegistryEntryResponse.model_validate(e) for e in entries],
        total=len(entries),
        active_count=active_count,
        disabled_count=disabled_count,
    )


@capabilities_router.get(
    "/registry/{registry_id}", response_model=RegistryEntryResponse
)
def get_registry_detail(
    registry_id: int,
    db: Session = Depends(_get_db),
):
    """Get details for a specific installed capability."""
    entry = get_registry_entry(db, registry_id)
    if entry is None:
        raise HTTPException(
            status_code=404, detail=f"Registry entry #{registry_id} not found"
        )
    return entry


@capabilities_router.post(
    "/registry/{registry_id}/failure",
    response_model=RegistryEntryResponse,
)
def record_failure(
    registry_id: int,
    db: Session = Depends(_get_db),
):
    """Record a runtime failure for an installed capability."""
    try:
        entry = record_capability_failure(db, registry_id)
        db.commit()
        db.refresh(entry)
        return entry
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
