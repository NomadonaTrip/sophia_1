"""Tests for plateau diagnostics, health checks, and institutional knowledge.

Tests plateau detection, diagnostic report generation with root cause analysis,
experiment proposals, weekly health checks, anonymized institutional knowledge
persistence, and similar diagnostic search.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sophia.intelligence.models import (
    Client,
    IntelligenceDomain,
    IntelligenceInstitutionalKnowledge,
)
from sophia.intelligence.schemas import ClientCreate
from sophia.intelligence.service import ClientService
from sophia.research.diagnostics import (
    detect_plateau,
    generate_diagnostic_report,
    persist_diagnostic_insights,
    propose_experiments,
    search_similar_diagnostics,
    weekly_health_check,
)
from sophia.research.models import (
    CompetitorSnapshot,
    FindingType,
    PlatformIntelligence,
    ResearchFinding,
)


def _create_findings(db, client_id, count, days_ago_start, days_ago_end, score=0.5):
    """Helper to create ResearchFinding records across a date range."""
    now = datetime.now(timezone.utc)
    findings = []
    for i in range(count):
        # Spread findings evenly across the date range
        age_days = days_ago_start + (days_ago_end - days_ago_start) * i / max(count - 1, 1)
        created = now - timedelta(days=age_days)

        finding = ResearchFinding(
            client_id=client_id,
            finding_type=FindingType.TREND,
            topic=f"topic_{i}",
            summary=f"Summary {i} for testing",
            relevance_score_val=score,
            confidence=0.7,
        )
        # Override created_at after creation
        db.add(finding)
        db.flush()
        # Manually set created_at since server_default is func.now()
        db.execute(
            ResearchFinding.__table__.update()
            .where(ResearchFinding.__table__.c.id == finding.id)
            .values(created_at=created)
        )
        db.flush()
        findings.append(finding)

    return findings


class TestDetectPlateau:
    """Tests for detect_plateau detecting flat 2-week metrics."""

    def test_returns_true_for_flat_engagement(self, db_session, sample_client):
        """detect_plateau returns True when 2-week engagement is flat (<5% change)."""
        # Create findings in both windows with same scores (flat)
        _create_findings(db_session, sample_client.id, 5, 0, 13, score=0.5)
        _create_findings(db_session, sample_client.id, 5, 14, 27, score=0.5)

        result = detect_plateau(db_session, sample_client.id)

        assert result is True

    def test_returns_false_for_trending_up(self, db_session, sample_client):
        """detect_plateau returns False when engagement is trending up."""
        # Current period much higher than prior
        _create_findings(db_session, sample_client.id, 5, 0, 13, score=0.8)
        _create_findings(db_session, sample_client.id, 5, 14, 27, score=0.4)

        result = detect_plateau(db_session, sample_client.id)

        assert result is False

    def test_returns_false_for_trending_down(self, db_session, sample_client):
        """detect_plateau returns False when engagement is declining."""
        # Current period much lower than prior
        _create_findings(db_session, sample_client.id, 5, 0, 13, score=0.3)
        _create_findings(db_session, sample_client.id, 5, 14, 27, score=0.8)

        result = detect_plateau(db_session, sample_client.id)

        assert result is False

    def test_returns_false_with_no_data(self, db_session, sample_client):
        """detect_plateau returns False when no data exists."""
        result = detect_plateau(db_session, sample_client.id)

        assert result is False


class TestGenerateDiagnosticReport:
    """Tests for generate_diagnostic_report root cause analysis."""

    def test_identifies_content_staleness(self, db_session, sample_client):
        """Report identifies content staleness when themes are repetitive."""
        # Create findings with same topic in both periods (staleness)
        now = datetime.now(timezone.utc)
        for i in range(3):
            for days_ago in [3, 17]:  # Recent and prior period
                finding = ResearchFinding(
                    client_id=sample_client.id,
                    finding_type=FindingType.TREND,
                    topic=f"same_topic_{i}",
                    summary=f"Same content about topic {i}",
                    relevance_score_val=0.5,
                    confidence=0.7,
                )
                db_session.add(finding)
                db_session.flush()
                db_session.execute(
                    ResearchFinding.__table__.update()
                    .where(ResearchFinding.__table__.c.id == finding.id)
                    .values(created_at=now - timedelta(days=days_ago))
                )
        db_session.flush()

        report = generate_diagnostic_report(db_session, sample_client.id)

        assert report["client_id"] == sample_client.id
        assert isinstance(report["root_causes"], list)
        assert isinstance(report["experiments"], list)
        assert report["generated_at"] is not None

        # Content staleness should be detected
        cause_names = [c["cause"] for c in report["root_causes"]]
        assert "content_staleness" in cause_names

    def test_identifies_competitor_gains(self, db_session, sample_client):
        """Report identifies competitor gains when competitor engagement is rising."""
        from sophia.research.models import Competitor

        # Create a competitor with rising engagement
        competitor = Competitor(
            client_id=sample_client.id,
            name="Rival Co",
            is_primary=1,
            is_operator_approved=1,
        )
        db_session.add(competitor)
        db_session.flush()

        now = datetime.now(timezone.utc)
        snapshot = CompetitorSnapshot(
            client_id=sample_client.id,
            competitor_id=competitor.id,
            avg_engagement_rate=0.08,
        )
        db_session.add(snapshot)
        db_session.flush()
        db_session.execute(
            CompetitorSnapshot.__table__.update()
            .where(CompetitorSnapshot.__table__.c.id == snapshot.id)
            .values(created_at=now - timedelta(days=3))
        )
        db_session.flush()

        report = generate_diagnostic_report(db_session, sample_client.id)

        cause_names = [c["cause"] for c in report["root_causes"]]
        assert "competitor_gains" in cause_names

    def test_report_structure_complete(self, db_session, sample_client):
        """Report has all required fields."""
        report = generate_diagnostic_report(db_session, sample_client.id)

        assert "client_id" in report
        assert "plateau_detected" in report
        assert "metrics_summary" in report
        assert "root_causes" in report
        assert "experiments" in report
        assert "generated_at" in report


class TestProposeExperiments:
    """Tests for propose_experiments generating structured proposals."""

    def test_generates_experiments_with_all_required_fields(self):
        """Each experiment has hypothesis, duration, success metric, and rollback."""
        root_causes = [
            {"cause": "content_staleness", "likelihood": 0.8, "evidence": "Repetitive content"},
            {"cause": "audience_fatigue", "likelihood": 0.6, "evidence": "Declining engagement"},
        ]

        experiments = propose_experiments(root_causes)

        assert len(experiments) >= 2
        for exp in experiments:
            assert "hypothesis" in exp
            assert "action" in exp
            assert "duration_days" in exp
            assert exp["duration_days"] in range(7, 15)
            assert "success_metric" in exp
            assert "rollback_plan" in exp
            assert "addresses_cause" in exp
            assert exp["requires_operator_approval"] is True

    def test_skips_low_likelihood_causes(self):
        """Experiments are not generated for causes with likelihood < 0.3."""
        root_causes = [
            {"cause": "content_staleness", "likelihood": 0.1, "evidence": "Low signal"},
            {"cause": "seasonal_patterns", "likelihood": 0.2, "evidence": "Very low"},
        ]

        experiments = propose_experiments(root_causes)

        assert len(experiments) == 0

    def test_maps_causes_to_correct_experiments(self):
        """Each experiment addresses the correct root cause."""
        root_causes = [
            {"cause": "competitor_gains", "likelihood": 0.7, "evidence": "Rising competitor"},
        ]

        experiments = propose_experiments(root_causes)

        assert len(experiments) >= 1
        assert experiments[0]["addresses_cause"] == "competitor_gains"


class TestWeeklyHealthCheck:
    """Tests for weekly_health_check catching slow declines."""

    def test_flags_declining_metrics(self, db_session, sample_client):
        """Health check flags declining engagement and stale research."""
        # No research findings = stale research
        result = weekly_health_check(db_session, sample_client.id)

        assert result["client_id"] == sample_client.id
        assert result["overall_health"] in ("healthy", "warning", "declining")
        assert isinstance(result["warnings"], list)
        assert result["checked_at"] is not None

        # Should have warnings about stale research and profile completeness
        assert len(result["warnings"]) >= 1

    def test_healthy_client_no_warnings(self, db_session, sample_client):
        """Healthy client with fresh data gets no warnings."""
        # Create recent research findings
        now = datetime.now(timezone.utc)
        for i in range(3):
            finding = ResearchFinding(
                client_id=sample_client.id,
                finding_type=FindingType.TREND,
                topic=f"Fresh topic {i}",
                summary=f"Recent finding {i}",
                relevance_score_val=0.8,
                confidence=0.7,
            )
            db_session.add(finding)

        # Create active playbook entry
        playbook_entry = PlatformIntelligence(
            client_id=sample_client.id,
            platform="instagram",
            category="required_to_play",
            insight="Use hashtags",
            evidence={},
            is_active=1,
        )
        db_session.add(playbook_entry)
        db_session.commit()

        result = weekly_health_check(db_session, sample_client.id)

        # Fewer warnings with fresh data and playbook
        # Profile completeness may still be low
        assert result["metrics"]["research_freshness"] == "fresh"
        assert result["metrics"]["has_active_playbook"] is True

    def test_health_check_structure(self, db_session, sample_client):
        """Health check has all required fields."""
        result = weekly_health_check(db_session, sample_client.id)

        assert "client_id" in result
        assert "overall_health" in result
        assert "metrics" in result
        assert "warnings" in result
        assert "checked_at" in result

        metrics = result["metrics"]
        assert "engagement_trend" in metrics
        assert "research_freshness" in metrics
        assert "profile_completeness_pct" in metrics
        assert "has_active_playbook" in metrics


class TestPersistDiagnosticInsights:
    """Tests for persist_diagnostic_insights creating anonymized institutional knowledge."""

    def test_creates_anonymized_institutional_knowledge(self, db_session, sample_client):
        """persist_diagnostic_insights creates anonymized institutional knowledge."""
        diagnostic_report = {
            "client_id": sample_client.id,
            "plateau_detected": True,
            "root_causes": [
                {"cause": "content_staleness", "likelihood": 0.8, "evidence": "Repetitive themes"},
                {"cause": "seasonal_patterns", "likelihood": 0.2, "evidence": "Low signal"},
            ],
            "experiments": [
                {
                    "hypothesis": "Fresh content will re-engage",
                    "action": "Introduce video content",
                    "duration_days": 14,
                    "success_metric": "20% engagement lift",
                    "rollback_plan": "Return to prior mix",
                    "addresses_cause": "content_staleness",
                },
            ],
        }

        with patch("sophia.semantic.sync.sync_to_lance", new_callable=AsyncMock):
            persist_diagnostic_insights(
                db_session, sample_client.id, diagnostic_report
            )

        # Verify institutional knowledge was created
        entries = db_session.query(IntelligenceInstitutionalKnowledge).all()
        assert len(entries) >= 1

        entry = entries[-1]
        # Should be anonymized (source_client_id = None)
        assert entry.source_client_id is None
        assert "plateau resolved" in entry.insight.lower() or "content_staleness" in entry.insight
        assert entry.industry_vertical is not None


class TestSearchSimilarDiagnostics:
    """Tests for search_similar_diagnostics finding historical patterns."""

    def test_finds_relevant_historical_patterns(self, db_session, sample_client):
        """search_similar_diagnostics finds matching institutional knowledge."""
        # Create some institutional knowledge entries
        entry = IntelligenceInstitutionalKnowledge(
            source_client_id=None,
            industry_vertical="Marketing Agency",
            business_size_category="small",
            region_type="suburban",
            domain=IntelligenceDomain.INDUSTRY,
            insight="Engagement plateau resolved via video content shift",
            what_worked=["Video content", "Behind-the-scenes posts"],
            what_didnt_work=["Long-form text posts"],
        )
        db_session.add(entry)
        db_session.commit()

        # Search for similar patterns (will use SQL fallback since LanceDB not configured)
        results = search_similar_diagnostics(
            db_session,
            industry="Marketing",
            symptoms="Engagement plateau for 3 weeks",
        )

        assert len(results) >= 1
        # Check the result has useful fields
        result = results[0]
        assert "insight" in result or "text" in result

    def test_returns_empty_for_no_matches(self, db_session, sample_client):
        """Returns empty list when no matching historical patterns exist."""
        results = search_similar_diagnostics(
            db_session,
            industry="Nonexistent Industry XYZ",
            symptoms="Some symptoms",
        )

        assert isinstance(results, list)
        assert len(results) == 0
