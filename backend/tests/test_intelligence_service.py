"""Tests for progressive intelligence enrichment service.

Uses SQLite in-memory database (via the conftest db_session fixture).
Mocks semantic search for deduplication tests.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sophia.intelligence.models import (
    IntelligenceDomain,
    IntelligenceEntry,
    IntelligenceInstitutionalKnowledge,
)
from sophia.intelligence.schemas import (
    DomainScore,
    ICPPersona,
    IntelligenceProfileResponse,
)
from sophia.intelligence.service import (
    ClientService,
    add_intelligence,
    assemble_customer_personas,
    compute_depth_scores,
    create_institutional_knowledge,
    detect_gaps,
    generate_strategic_narrative,
    get_profile_summary,
)


def _run(coro):
    """Helper to run async functions in sync tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestAddIntelligence:
    """Tests for add_intelligence with deduplication and write-through sync."""

    def test_creates_new_entry(self, db_session, sample_client):
        """add_intelligence creates a new IntelligenceEntry in the database."""
        with patch("sophia.semantic.sync.sync_to_lance") as mock_sync:
            entry = _run(
                add_intelligence(
                    db_session,
                    client_id=sample_client.id,
                    domain=IntelligenceDomain.BUSINESS,
                    fact="Local bakery serving Hamilton area since 2015",
                    source="operator:conversation",
                    confidence=0.8,
                )
            )

        assert entry.id is not None
        assert entry.client_id == sample_client.id
        assert entry.domain == IntelligenceDomain.BUSINESS
        assert entry.fact == "Local bakery serving Hamilton area since 2015"
        assert entry.confidence == 0.8

    def test_triggers_write_through_sync(self, db_session, sample_client):
        """add_intelligence calls sync_to_lance after SQLite commit."""
        with patch("sophia.semantic.sync.sync_to_lance", new_callable=AsyncMock) as mock_sync:
            entry = _run(
                add_intelligence(
                    db_session,
                    client_id=sample_client.id,
                    domain=IntelligenceDomain.INDUSTRY,
                    fact="Marketing agencies in Ontario growing 15% YoY",
                    source="research:finding_id:42",
                    confidence=0.6,
                )
            )

            assert mock_sync.called
            call_kwargs = mock_sync.call_args
            assert call_kwargs[1]["record_type"] == "intelligence_entries" or \
                   (len(call_kwargs[0]) > 0 and call_kwargs[0][0] == "intelligence_entries")

    def test_deduplication_exact_match(self, db_session, sample_client):
        """Adding the same fact updates existing entry instead of creating duplicate."""
        with patch("sophia.semantic.sync.sync_to_lance", new_callable=AsyncMock) as mock_sync:

            entry1 = _run(
                add_intelligence(
                    db_session,
                    client_id=sample_client.id,
                    domain=IntelligenceDomain.BUSINESS,
                    fact="Specializes in wedding cakes",
                    source="operator:conversation",
                    confidence=0.7,
                )
            )

            entry2 = _run(
                add_intelligence(
                    db_session,
                    client_id=sample_client.id,
                    domain=IntelligenceDomain.BUSINESS,
                    fact="Specializes in wedding cakes",
                    source="web:website",
                    confidence=0.9,
                )
            )

        # Should return the same entry (updated, not duplicated)
        assert entry1.id == entry2.id
        # Confidence should be max of both
        assert entry2.confidence == 0.9

    def test_significant_entry_flag(self, db_session, sample_client):
        """is_significant flag is stored correctly."""
        with patch("sophia.semantic.sync.sync_to_lance", new_callable=AsyncMock) as mock_sync:

            entry = _run(
                add_intelligence(
                    db_session,
                    client_id=sample_client.id,
                    domain=IntelligenceDomain.COMPETITORS,
                    fact="New competitor opened across the street",
                    source="operator:conversation",
                    confidence=0.95,
                    is_significant=True,
                )
            )

        assert entry.is_significant == 1


class TestComputeDepthScores:
    """Tests for depth scoring across intelligence domains."""

    def test_empty_client_returns_zero_scores(self, db_session, sample_client):
        """Client with no intelligence entries gets 0 depth for all domains."""
        scores = compute_depth_scores(db_session, sample_client.id)

        assert len(scores) == 6  # Six domains
        for score in scores:
            assert score.depth == 0.0
            assert score.entry_count == 0

    def test_scores_increase_with_entries(self, db_session, sample_client):
        """Adding entries to a domain increases its depth score."""
        with patch("sophia.semantic.sync.sync_to_lance", new_callable=AsyncMock) as mock_sync:

            for i in range(4):
                _run(
                    add_intelligence(
                        db_session,
                        client_id=sample_client.id,
                        domain=IntelligenceDomain.BUSINESS,
                        fact=f"Business fact {i}: unique detail {i * 100}",
                        source=f"source_{i}:detail",
                        confidence=0.7,
                    )
                )

        scores = compute_depth_scores(db_session, sample_client.id)
        business_score = next(
            s for s in scores if s.domain == IntelligenceDomain.BUSINESS.value
        )

        assert business_score.depth > 0
        assert business_score.entry_count == 4
        assert business_score.freshness > 0

    def test_depth_within_1_to_5_range(self, db_session, sample_client):
        """Depth scores are always within 0-5 range."""
        with patch("sophia.semantic.sync.sync_to_lance", new_callable=AsyncMock) as mock_sync:

            for i in range(10):
                _run(
                    add_intelligence(
                        db_session,
                        client_id=sample_client.id,
                        domain=IntelligenceDomain.INDUSTRY,
                        fact=f"Industry insight {i}: detail {i * 200}",
                        source=f"research:finding:{i}",
                        confidence=0.9,
                    )
                )

        scores = compute_depth_scores(db_session, sample_client.id)
        for score in scores:
            assert 0 <= score.depth <= 5


class TestDetectGaps:
    """Tests for gap detection in intelligence profiles."""

    def test_detects_empty_domains(self, db_session, sample_client):
        """detect_gaps identifies domains with no entries."""
        gaps = detect_gaps(db_session, sample_client.id)

        # All 6 domains should be flagged as empty
        assert len(gaps) == 6
        for gap in gaps:
            assert "no intelligence entries" in gap

    def test_detects_low_depth_domains(self, db_session, sample_client):
        """detect_gaps identifies domains with depth < 2."""
        with patch("sophia.semantic.sync.sync_to_lance", new_callable=AsyncMock) as mock_sync:

            # Add just one entry to BUSINESS domain (depth will be < 2)
            _run(
                add_intelligence(
                    db_session,
                    client_id=sample_client.id,
                    domain=IntelligenceDomain.BUSINESS,
                    fact="Small landscaping company in Guelph",
                    source="operator:conversation",
                    confidence=0.5,
                )
            )

        gaps = detect_gaps(db_session, sample_client.id)

        # BUSINESS should still be flagged (low depth)
        business_gaps = [g for g in gaps if "Business" in g]
        assert len(business_gaps) >= 1

    def test_detects_customers_persona_shortage(self, db_session, sample_client):
        """detect_gaps flags CUSTOMERS domain when fewer than 2 personas assembled."""
        with patch("sophia.semantic.sync.sync_to_lance", new_callable=AsyncMock) as mock_sync:

            # Add a single CUSTOMERS entry (not enough for 2 personas)
            _run(
                add_intelligence(
                    db_session,
                    client_id=sample_client.id,
                    domain=IntelligenceDomain.CUSTOMERS,
                    fact="Primary audience is homeowners aged 35-55",
                    source="operator:conversation",
                    confidence=0.7,
                )
            )

        gaps = detect_gaps(db_session, sample_client.id)

        persona_gaps = [g for g in gaps if "persona" in g.lower()]
        assert len(persona_gaps) >= 1
        assert "minimum personas" in persona_gaps[0].lower() or "persona" in persona_gaps[0].lower()


class TestGenerateStrategicNarrative:
    """Tests for strategic narrative generation."""

    def test_returns_empty_string_when_no_entries(self, db_session, sample_client):
        """generate_strategic_narrative returns empty string for client with no entries."""
        narrative = _run(
            generate_strategic_narrative(db_session, sample_client.id)
        )

        assert narrative == ""

    def test_produces_paragraphs_from_domain_entries(self, db_session, sample_client):
        """generate_strategic_narrative produces multi-paragraph summary from entries."""
        with patch("sophia.semantic.sync.sync_to_lance", new_callable=AsyncMock) as mock_sync:

            # Add entries to multiple domains
            _run(
                add_intelligence(
                    db_session,
                    client_id=sample_client.id,
                    domain=IntelligenceDomain.BUSINESS,
                    fact="Established landscaping company serving Hamilton since 2010",
                    source="operator:conversation",
                    confidence=0.9,
                )
            )
            _run(
                add_intelligence(
                    db_session,
                    client_id=sample_client.id,
                    domain=IntelligenceDomain.CUSTOMERS,
                    fact="Primary customers are suburban homeowners with properties over 0.5 acres",
                    source="research:finding:5",
                    confidence=0.8,
                )
            )
            _run(
                add_intelligence(
                    db_session,
                    client_id=sample_client.id,
                    domain=IntelligenceDomain.PRODUCT_SERVICE,
                    fact="Offers lawn maintenance, garden design, and snow removal services",
                    source="web:website",
                    confidence=0.85,
                )
            )

        narrative = _run(
            generate_strategic_narrative(db_session, sample_client.id)
        )

        assert len(narrative) > 0
        # Should have multiple paragraphs (separated by double newline)
        paragraphs = [p for p in narrative.split("\n\n") if p.strip()]
        assert len(paragraphs) >= 2


class TestAssembleCustomerPersonas:
    """Tests for customer persona assembly from CUSTOMERS domain entries."""

    def test_returns_empty_when_no_entries(self, db_session, sample_client):
        """assemble_customer_personas returns empty list when no CUSTOMERS entries."""
        personas = _run(
            assemble_customer_personas(db_session, sample_client.id)
        )

        assert personas == []

    def test_clusters_entries_into_personas(self, db_session, sample_client):
        """assemble_customer_personas creates named ICPPersona objects."""
        with patch("sophia.semantic.sync.sync_to_lance", new_callable=AsyncMock) as mock_sync:

            # Add multiple CUSTOMERS entries
            _run(
                add_intelligence(
                    db_session,
                    client_id=sample_client.id,
                    domain=IntelligenceDomain.CUSTOMERS,
                    fact="Homeowners aged 35-55 struggle with maintaining large properties",
                    source="research:finding:10",
                    confidence=0.8,
                )
            )
            _run(
                add_intelligence(
                    db_session,
                    client_id=sample_client.id,
                    domain=IntelligenceDomain.CUSTOMERS,
                    fact="Young professionals aged 25-35 prefer low-maintenance garden designs",
                    source="research:finding:11",
                    confidence=0.7,
                )
            )

        personas = _run(
            assemble_customer_personas(db_session, sample_client.id)
        )

        assert len(personas) >= 1
        for persona in personas:
            assert isinstance(persona, ICPPersona)
            assert persona.name
            assert persona.demographics


class TestGetProfileSummary:
    """Tests for full profile summary assembly."""

    def test_includes_strategic_narrative(self, db_session, sample_client):
        """get_profile_summary includes strategic_narrative in response."""
        with patch("sophia.semantic.sync.sync_to_lance", new_callable=AsyncMock) as mock_sync:

            _run(
                add_intelligence(
                    db_session,
                    client_id=sample_client.id,
                    domain=IntelligenceDomain.BUSINESS,
                    fact="Digital marketing agency in Kitchener-Waterloo",
                    source="operator:conversation",
                    confidence=0.9,
                )
            )

        profile = _run(
            get_profile_summary(db_session, sample_client.id)
        )

        assert isinstance(profile, IntelligenceProfileResponse)
        assert profile.client_id == sample_client.id
        assert profile.strategic_narrative is not None
        assert len(profile.domain_scores) == 6
        assert profile.overall_completeness >= 0

    def test_completeness_increases_with_data(self, db_session, sample_client):
        """overall_completeness increases as more domains have data."""
        # Empty profile
        profile_empty = _run(
            get_profile_summary(db_session, sample_client.id)
        )

        with patch("sophia.semantic.sync.sync_to_lance", new_callable=AsyncMock) as mock_sync:

            # Add entries to multiple domains
            for domain in [
                IntelligenceDomain.BUSINESS,
                IntelligenceDomain.INDUSTRY,
                IntelligenceDomain.CUSTOMERS,
            ]:
                for i in range(3):
                    _run(
                        add_intelligence(
                            db_session,
                            client_id=sample_client.id,
                            domain=domain,
                            fact=f"{domain.value} fact {i}: unique detail {i * 300}",
                            source=f"research:finding:{i}",
                            confidence=0.8,
                        )
                    )

        profile_enriched = _run(
            get_profile_summary(db_session, sample_client.id)
        )

        assert profile_enriched.overall_completeness > profile_empty.overall_completeness


class TestCreateInstitutionalKnowledge:
    """Tests for anonymized institutional knowledge creation."""

    def test_strips_identifying_info(self, db_session, sample_client):
        """create_institutional_knowledge strips client name from insight."""
        with patch("sophia.semantic.sync.sync_to_lance", new_callable=AsyncMock) as mock_sync:

            entry = _run(
                create_institutional_knowledge(
                    db_session,
                    client_id=sample_client.id,
                    domain=IntelligenceDomain.CUSTOMERS,
                    insight=f"Customers of {sample_client.name} prefer evening browsing",
                    what_worked=["Before/after photos", "Video testimonials"],
                    what_didnt_work=["Long-form blog posts"],
                )
            )

        assert isinstance(entry, IntelligenceInstitutionalKnowledge)
        # Client name should be stripped
        assert sample_client.name not in entry.insight
        assert "[business]" in entry.insight
        # Source client ID should be None (anonymized)
        assert entry.source_client_id is None
        assert entry.what_worked == ["Before/after photos", "Video testimonials"]
        assert entry.what_didnt_work == ["Long-form blog posts"]

    def test_derives_business_size(self, db_session, sample_client):
        """create_institutional_knowledge derives business_size_category from client."""
        with patch("sophia.semantic.sync.sync_to_lance", new_callable=AsyncMock) as mock_sync:

            entry = _run(
                create_institutional_knowledge(
                    db_session,
                    client_id=sample_client.id,
                    domain=IntelligenceDomain.BUSINESS,
                    insight="Small businesses in this industry benefit from community engagement",
                    what_worked=["Community events"],
                )
            )

        assert entry.business_size_category in ("micro", "small", "medium")
        assert entry.region_type in ("small_town", "suburban", "urban")
        assert entry.industry_vertical is not None
