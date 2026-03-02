"""Tests for skill classification and governance.

Covers risk classification (safe/risky), auto-acquisition of safe skills,
queuing of risky skills, and batch governance processing.
"""

from datetime import datetime, timezone

import pytest

from sophia.capabilities.models import (
    CapabilityGap,
    CapabilityProposal,
    DiscoveredCapability,
    GapStatus,
    ProposalStatus,
)
from sophia.orchestrator.skill_governance import (
    auto_acquire_safe_skill,
    classify_skill_risk,
    process_proposals_with_governance,
    queue_risky_skill,
)


# -- Helpers ------------------------------------------------------------------


def _make_gap(db_session, description="Test gap"):
    """Create a CapabilityGap for test scaffolding."""
    gap = CapabilityGap(
        description=description,
        detected_during="test_stage",
        status=GapStatus.proposals_ready.value,
    )
    db_session.add(gap)
    db_session.flush()
    return gap


def _make_discovered(db_session, gap, *, source="mcp_registry", name="test-cap",
                     description="A test capability"):
    """Create a DiscoveredCapability linked to a gap."""
    disc = DiscoveredCapability(
        gap_id=gap.id,
        source=source,
        name=name,
        description=description,
        url=f"https://github.com/example/{name}",
    )
    db_session.add(disc)
    db_session.flush()
    return disc


def _make_proposal(db_session, gap, disc, *, status=ProposalStatus.pending.value):
    """Create a CapabilityProposal linked to a gap and discovered capability."""
    proposal = CapabilityProposal(
        gap_id=gap.id,
        discovered_id=disc.id,
        relevance_score=4,
        quality_score=4,
        security_score=4,
        fit_score=4,
        composite_score=4.0,
        recommendation="recommend",
        auto_rejected=False,
        justification_json="{}",
        status=status,
    )
    db_session.add(proposal)
    db_session.flush()
    return proposal


# =============================================================================
# Classification tests
# =============================================================================


class TestClassifySkillRisk:
    """Test keyword-based risk classification."""

    def test_classify_safe_research_tool(self, db_session):
        """MCP server that searches Reddit is classified as safe."""
        gap = _make_gap(db_session)
        disc = _make_discovered(
            db_session, gap,
            source="mcp_server",
            name="reddit-trends-mcp",
            description="Searches Reddit for trending topics",
        )

        result = classify_skill_risk(disc)

        assert result == "safe"

    def test_classify_safe_analytics(self, db_session):
        """Analytics capability reading engagement metrics is safe."""
        gap = _make_gap(db_session)
        disc = _make_discovered(
            db_session, gap,
            source="mcp_registry",
            name="meta-analytics-mcp",
            description="Reads engagement metrics from Meta API",
        )

        result = classify_skill_risk(disc)

        assert result == "safe"

    def test_classify_risky_publisher(self, db_session):
        """Capability that posts content to Facebook is risky."""
        gap = _make_gap(db_session)
        disc = _make_discovered(
            db_session, gap,
            source="mcp_registry",
            name="facebook-publisher",
            description="Posts content to Facebook page",
        )

        result = classify_skill_risk(disc)

        assert result == "risky"

    def test_classify_risky_payment(self, db_session):
        """Capability that charges credit cards is risky."""
        gap = _make_gap(db_session)
        disc = _make_discovered(
            db_session, gap,
            source="github",
            name="stripe-mcp",
            description="Charges client credit card via Stripe",
        )

        result = classify_skill_risk(disc)

        assert result == "risky"

    def test_classify_unknown_defaults_risky(self, db_session):
        """Vague description with no clear indicators defaults to risky."""
        gap = _make_gap(db_session)
        disc = _make_discovered(
            db_session, gap,
            source="github",
            name="mysterious-tool",
            description="Does something with data",
        )

        result = classify_skill_risk(disc)

        assert result == "risky"


# =============================================================================
# Governance action tests
# =============================================================================


class TestAutoAcquireSafeSkill:
    """Test auto-acquisition of safe capabilities."""

    def test_auto_acquire_safe_skill(self, db_session):
        """Safe skill proposal is auto-approved and creates registry entry."""
        gap = _make_gap(db_session)
        disc = _make_discovered(
            db_session, gap,
            source="mcp_registry",
            name="reddit-search-mcp",
            description="Searches Reddit for trending topics in a given subreddit",
        )
        proposal = _make_proposal(db_session, gap, disc)

        registry = auto_acquire_safe_skill(db_session, proposal.id)

        assert registry is not None
        assert registry.name == "reddit-search-mcp"
        assert registry.status == "active"
        assert proposal.status == "approved"
        assert "Auto-acquired" in proposal.review_notes

    def test_auto_acquire_rejects_risky(self, db_session):
        """Risky capability proposal is not auto-acquired, returns None."""
        gap = _make_gap(db_session)
        disc = _make_discovered(
            db_session, gap,
            source="mcp_registry",
            name="facebook-poster",
            description="Posts content to Facebook pages on behalf of clients",
        )
        proposal = _make_proposal(db_session, gap, disc)

        result = auto_acquire_safe_skill(db_session, proposal.id)

        assert result is None
        assert proposal.status == "pending"  # Still pending


# =============================================================================
# Batch governance tests
# =============================================================================


class TestProcessProposalsWithGovernance:
    """Test batch governance processing of pending proposals."""

    def test_process_proposals_mixed(self, db_session):
        """2 safe + 1 risky proposals yields correct auto_acquired/queued counts."""
        # Safe proposal 1: search tool
        gap1 = _make_gap(db_session, "Need Reddit search tool")
        disc1 = _make_discovered(
            db_session, gap1,
            source="mcp_registry",
            name="reddit-search-mcp",
            description="Searches Reddit for trending topics",
        )
        _make_proposal(db_session, gap1, disc1)

        # Safe proposal 2: analytics tool
        gap2 = _make_gap(db_session, "Need engagement analytics reader")
        disc2 = _make_discovered(
            db_session, gap2,
            source="mcp_registry",
            name="meta-analytics-reader",
            description="Reads engagement metrics from Meta API and analyzes trends",
        )
        _make_proposal(db_session, gap2, disc2)

        # Risky proposal: publisher
        gap3 = _make_gap(db_session, "Need Facebook publisher")
        disc3 = _make_discovered(
            db_session, gap3,
            source="mcp_registry",
            name="facebook-publisher",
            description="Posts content to Facebook page",
        )
        _make_proposal(db_session, gap3, disc3)

        result = process_proposals_with_governance(db_session)

        assert result["auto_acquired"] == 2
        assert result["queued_for_approval"] == 1
