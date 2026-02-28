"""Tests for the decision trace pipeline: capture, attribution, quality evaluation,
and feedback loop.

Validates that decision traces are captured at every content cycle stage, outcomes
are attributed back to specific decisions, quality scores are computed correctly,
and feedback context is structured for generation prompt injection.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from sophia.analytics.decision_trace import (
    ALLOWED_STAGES,
    MAX_EVIDENCE_KEYS,
    attribute_batch,
    attribute_outcomes,
    capture_approval_decision,
    capture_decision,
    capture_gate_decision,
    capture_generation_decisions,
    compute_decision_quality,
    evaluate_decision_quality_batch,
    get_decision_quality_context,
)
from sophia.analytics.models import (
    DecisionQualityScore,
    DecisionTrace,
    EngagementMetric,
)
from sophia.content.models import ContentDraft


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_draft(db_session, sample_client):
    """Create a content draft for trace tests."""
    draft = ContentDraft(
        client_id=sample_client.id,
        platform="instagram",
        content_type="feed",
        copy="Beautiful spring garden with fresh flowers blooming",
        image_prompt="A vibrant spring garden scene",
        image_ratio="4:5",
        gate_status="passed",
        status="published",
        content_pillar="seasonal",
        voice_confidence_pct=78.0,
    )
    db_session.add(draft)
    db_session.flush()
    return draft


@pytest.fixture
def sample_draft_2(db_session, sample_client):
    """Create a second content draft for batch tests."""
    draft = ContentDraft(
        client_id=sample_client.id,
        platform="facebook",
        content_type="feed",
        copy="Local tips for summer lawn care maintenance",
        image_prompt="A well-maintained lawn",
        image_ratio="1:1",
        gate_status="passed",
        status="published",
        content_pillar="education",
    )
    db_session.add(draft)
    db_session.flush()
    return draft


# ---------------------------------------------------------------------------
# Test: capture_decision
# ---------------------------------------------------------------------------


class TestCaptureDecision:
    """Tests for the core capture_decision function."""

    def test_creates_trace_with_correct_fields(self, db_session, sample_client, sample_draft):
        """capture_decision creates a DecisionTrace with all fields populated."""
        trace = capture_decision(
            db=db_session,
            draft_id=sample_draft.id,
            client_id=sample_client.id,
            stage="research",
            decision="Used 3 research sources on spring gardening trends",
            alternatives=["competitor analysis", "trend monitoring"],
            rationale="Spring content performs best in March-April window",
            evidence={"source_count": 3, "confidence": 0.85},
            confidence=0.85,
            predicted_outcome={"engagement_rate": 0.05},
        )

        assert trace.id is not None
        assert trace.content_draft_id == sample_draft.id
        assert trace.client_id == sample_client.id
        assert trace.stage == "research"
        assert trace.decision == "Used 3 research sources on spring gardening trends"
        assert trace.alternatives_considered == ["competitor analysis", "trend monitoring"]
        assert trace.rationale == "Spring content performs best in March-April window"
        assert trace.evidence == {"source_count": 3, "confidence": 0.85}
        assert trace.confidence == 0.85
        assert trace.predicted_outcome == {"engagement_rate": 0.05}
        assert trace.actual_outcome is None

    def test_validates_stage_in_allowed_set(self, db_session, sample_client, sample_draft):
        """capture_decision raises ValueError for invalid stage."""
        with pytest.raises(ValueError, match="Invalid stage 'invalid_stage'"):
            capture_decision(
                db=db_session,
                draft_id=sample_draft.id,
                client_id=sample_client.id,
                stage="invalid_stage",
                decision="test",
            )

    def test_caps_evidence_to_5_items(self, db_session, sample_client, sample_draft):
        """capture_decision caps evidence dict to MAX_EVIDENCE_KEYS items."""
        large_evidence = {f"key_{i}": f"value_{i}" for i in range(10)}
        trace = capture_decision(
            db=db_session,
            draft_id=sample_draft.id,
            client_id=sample_client.id,
            stage="research",
            decision="test",
            evidence=large_evidence,
        )

        assert len(trace.evidence) == MAX_EVIDENCE_KEYS

    def test_all_allowed_stages(self, db_session, sample_client, sample_draft):
        """Every allowed stage is accepted without error."""
        for stage in ALLOWED_STAGES:
            trace = capture_decision(
                db=db_session,
                draft_id=sample_draft.id,
                client_id=sample_client.id,
                stage=stage,
                decision=f"Test decision for {stage}",
            )
            assert trace.stage == stage

    def test_minimal_fields(self, db_session, sample_client, sample_draft):
        """capture_decision works with only required fields."""
        trace = capture_decision(
            db=db_session,
            draft_id=sample_draft.id,
            client_id=sample_client.id,
            stage="angle",
            decision="Seasonal angle chosen",
        )

        assert trace.id is not None
        assert trace.alternatives_considered is None
        assert trace.rationale is None
        assert trace.evidence is None
        assert trace.confidence is None
        assert trace.predicted_outcome is None


# ---------------------------------------------------------------------------
# Test: capture_generation_decisions
# ---------------------------------------------------------------------------


class TestCaptureGenerationDecisions:
    """Tests for the generation-phase convenience capture function."""

    def test_creates_4_traces(self, db_session, sample_client, sample_draft):
        """capture_generation_decisions creates traces for research, angle, persona, format."""
        traces = capture_generation_decisions(
            db=db_session,
            draft=sample_draft,
            generation_context={
                "research_ids": [1, 2, 3],
                "angle": "seasonal tips",
                "persona": "homeowner 35-55",
                "format_alternatives": ["carousel", "reel"],
            },
        )

        assert len(traces) == 4
        stages = [t.stage for t in traces]
        assert "research" in stages
        assert "angle" in stages
        assert "persona" in stages
        assert "format" in stages

    def test_extracts_draft_fields(self, db_session, sample_client, sample_draft):
        """capture_generation_decisions uses draft.content_pillar and platform."""
        traces = capture_generation_decisions(
            db=db_session,
            draft=sample_draft,
            generation_context={},
        )

        angle_trace = next(t for t in traces if t.stage == "angle")
        assert "seasonal" in angle_trace.decision

        format_trace = next(t for t in traces if t.stage == "format")
        assert "feed" in format_trace.decision
        assert "instagram" in format_trace.decision


# ---------------------------------------------------------------------------
# Test: capture_gate_decision
# ---------------------------------------------------------------------------


class TestCaptureGateDecision:
    """Tests for the quality gate decision capture."""

    def test_records_gate_status_as_decision(self, db_session, sample_client, sample_draft):
        """capture_gate_decision records gate_status as the decision."""
        gate_report = {
            "status": "passed",
            "results": [
                {"gate_name": "sensitivity", "status": "passed", "score": 1.0},
                {"gate_name": "voice_alignment", "status": "passed", "score": 0.85},
            ],
            "rejected_by": None,
            "summary_badge": "Passed all gates",
        }

        trace = capture_gate_decision(db_session, sample_draft, gate_report)

        assert trace.stage == "gate"
        assert trace.decision == "passed"
        assert trace.evidence["gates_passed"] == 2
        assert trace.evidence["gates_total"] == 2

    def test_records_rejection_info(self, db_session, sample_client, sample_draft):
        """capture_gate_decision includes rejected_by in evidence when rejected."""
        gate_report = {
            "status": "rejected",
            "results": [
                {"gate_name": "sensitivity", "status": "rejected", "score": 0.0},
            ],
            "rejected_by": "sensitivity",
            "summary_badge": "Rejected (sensitivity)",
        }

        trace = capture_gate_decision(db_session, sample_draft, gate_report)

        assert trace.decision == "rejected"
        assert trace.evidence["rejected_by"] == "sensitivity"
        assert trace.confidence == 0.5


# ---------------------------------------------------------------------------
# Test: capture_approval_decision
# ---------------------------------------------------------------------------


class TestCaptureApprovalDecision:
    """Tests for the approval decision capture."""

    def test_records_action_and_actor(self, db_session, sample_client, sample_draft):
        """capture_approval_decision records the approval action and actor."""
        trace = capture_approval_decision(
            db=db_session,
            draft_id=sample_draft.id,
            client_id=sample_client.id,
            action="approved",
            actor="operator:web",
        )

        assert trace.stage == "approval"
        assert trace.decision == "approved"
        assert trace.evidence == {"actor": "operator:web"}
        assert trace.confidence == 1.0


# ---------------------------------------------------------------------------
# Test: attribute_outcomes
# ---------------------------------------------------------------------------


class TestAttributeOutcomes:
    """Tests for the outcome attribution function."""

    def test_fills_actual_outcome_on_all_traces(self, db_session, sample_client, sample_draft):
        """attribute_outcomes fills actual_outcome on all traces for a draft."""
        # Create some traces
        capture_decision(
            db_session, sample_draft.id, sample_client.id,
            "research", "Test research decision",
        )
        capture_decision(
            db_session, sample_draft.id, sample_client.id,
            "angle", "Test angle decision",
        )

        # Create engagement metrics
        for name, value in [("engagement_rate", 0.045), ("save_rate", 0.012), ("reach", 3200.0)]:
            metric = EngagementMetric(
                client_id=sample_client.id,
                content_draft_id=sample_draft.id,
                platform="instagram",
                metric_name=name,
                metric_value=value,
                metric_date=date(2026, 2, 28),
                is_algorithm_dependent=(name == "reach"),
                period="day",
            )
            db_session.add(metric)
        db_session.flush()

        # Attribute outcomes
        traces = attribute_outcomes(db_session, sample_draft.id)

        assert len(traces) == 2
        for trace in traces:
            assert trace.actual_outcome is not None
            assert trace.actual_outcome["engagement_rate"] == 0.045
            assert trace.actual_outcome["save_rate"] == 0.012
            assert trace.actual_outcome["reach"] == 3200.0

    def test_with_no_metrics_returns_traces_unchanged(self, db_session, sample_client, sample_draft):
        """attribute_outcomes with no metrics returns traces without actual_outcome."""
        capture_decision(
            db_session, sample_draft.id, sample_client.id,
            "research", "Test decision",
        )

        traces = attribute_outcomes(db_session, sample_draft.id)

        assert len(traces) == 1
        assert traces[0].actual_outcome is None


# ---------------------------------------------------------------------------
# Test: compute_decision_quality
# ---------------------------------------------------------------------------


class TestComputeDecisionQuality:
    """Tests for the quality computation function."""

    def test_returns_1_for_perfect_prediction(self):
        """Perfect prediction (actual == predicted) returns quality 1.0."""
        predicted = {"engagement_rate": 0.05, "save_rate": 0.01, "reach": 3000}
        actual = {"engagement_rate": 0.05, "save_rate": 0.01, "reach": 3000}

        score = compute_decision_quality(predicted, actual, "topic_selection")
        assert score == pytest.approx(1.0, abs=0.01)

    def test_returns_less_than_1_for_imperfect_prediction(self):
        """Imperfect prediction returns quality < 1.0."""
        predicted = {"engagement_rate": 0.05, "save_rate": 0.01, "reach": 3000}
        actual = {"engagement_rate": 0.03, "save_rate": 0.005, "reach": 1500}

        score = compute_decision_quality(predicted, actual, "topic_selection")
        assert 0.0 < score < 1.0

    def test_returns_0_with_zero_predicted(self):
        """Zero predicted values are skipped (cannot compute ratio). All-zero returns 0."""
        predicted = {"engagement_rate": 0, "save_rate": 0, "reach": 0}
        actual = {"engagement_rate": 0.05, "save_rate": 0.01, "reach": 3000}

        score = compute_decision_quality(predicted, actual, "topic_selection")
        assert score == 0.0

    def test_empty_dicts_return_0(self):
        """Empty predicted or actual dicts return 0."""
        assert compute_decision_quality({}, {"engagement_rate": 0.05}, "topic_selection") == 0.0
        assert compute_decision_quality({"engagement_rate": 0.05}, {}, "topic_selection") == 0.0

    def test_over_prediction_capped_at_2x(self):
        """Actual exceeding 2x predicted is capped (ratio capped at 2.0)."""
        predicted = {"engagement_rate": 0.01}
        actual = {"engagement_rate": 0.10}  # 10x over-prediction

        score = compute_decision_quality(predicted, actual, "topic_selection")
        # ratio = min(0.10/0.01, 2.0) = 2.0, quality = 1.0 - |1.0 - 2.0| = 0.0
        assert score == pytest.approx(0.0, abs=0.01)


# ---------------------------------------------------------------------------
# Test: evaluate_decision_quality_batch
# ---------------------------------------------------------------------------


class TestEvaluateDecisionQualityBatch:
    """Tests for batch quality evaluation."""

    def test_creates_quality_score_records(self, db_session, sample_client, sample_draft):
        """evaluate_decision_quality_batch creates DecisionQualityScore records."""
        # Create traces with predicted outcomes
        capture_decision(
            db_session, sample_draft.id, sample_client.id,
            "research", "Test decision",
            predicted_outcome={"engagement_rate": 0.05, "save_rate": 0.01, "reach": 3000},
        )

        # Manually set actual_outcome
        trace = db_session.query(DecisionTrace).filter_by(
            content_draft_id=sample_draft.id, stage="research"
        ).first()
        trace.actual_outcome = {"engagement_rate": 0.045, "save_rate": 0.012, "reach": 3200}
        db_session.flush()

        # Evaluate
        period_start = date(2026, 1, 1)
        period_end = date(2026, 12, 31)
        scores = evaluate_decision_quality_batch(
            db_session, sample_client.id, period_start, period_end
        )

        assert len(scores) >= 1
        for score in scores:
            assert isinstance(score, DecisionQualityScore)
            assert score.avg_quality_score is not None
            assert 0.0 <= score.avg_quality_score <= 1.0
            assert score.sample_count >= 1


# ---------------------------------------------------------------------------
# Test: get_decision_quality_context
# ---------------------------------------------------------------------------


class TestGetDecisionQualityContext:
    """Tests for the feedback loop context function."""

    def test_returns_structured_dict(self, db_session, sample_client):
        """get_decision_quality_context returns dict with decision_quality and guidance."""
        # Create a quality score record
        qs = DecisionQualityScore(
            client_id=sample_client.id,
            decision_type="topic_selection",
            period_start=date(2026, 2, 1),
            period_end=date(2026, 2, 28),
            sample_count=15,
            avg_quality_score=0.72,
            scores_detail={"best_performing": ["educational", "seasonal"]},
        )
        db_session.add(qs)
        db_session.flush()

        context = get_decision_quality_context(db_session, sample_client.id)

        assert "decision_quality" in context
        assert "guidance" in context
        assert "topic_selection" in context["decision_quality"]
        assert context["decision_quality"]["topic_selection"]["avg_score"] == 0.72
        assert context["decision_quality"]["topic_selection"]["sample_count"] == 15

    def test_returns_empty_dict_on_cold_start(self, db_session, sample_client):
        """get_decision_quality_context returns empty dict when no quality data exists."""
        context = get_decision_quality_context(db_session, sample_client.id)
        assert context == {}


# ---------------------------------------------------------------------------
# Test: Integration (capture -> attribute -> evaluate -> feedback)
# ---------------------------------------------------------------------------


class TestFullPipeline:
    """Integration test for the complete decision trace pipeline."""

    def test_capture_attribute_evaluate_feedback(self, db_session, sample_client, sample_draft):
        """Full pipeline: capture -> attribute -> evaluate -> feedback loop."""
        # 1. CAPTURE: Record decisions during content generation
        traces = capture_generation_decisions(
            db=db_session,
            draft=sample_draft,
            generation_context={
                "research_ids": [1, 2],
                "angle": "seasonal tips",
                "persona": "homeowner",
            },
        )
        assert len(traces) == 4

        # Add predicted outcomes to some traces
        for trace in traces:
            trace.predicted_outcome = {
                "engagement_rate": 0.05,
                "save_rate": 0.01,
                "reach": 3000,
            }
        db_session.flush()

        # 2. ATTRIBUTE: Add engagement metrics and attribute outcomes
        for name, value in [
            ("engagement_rate", 0.045),
            ("save_rate", 0.012),
            ("reach", 3200.0),
            ("likes", 120.0),
        ]:
            metric = EngagementMetric(
                client_id=sample_client.id,
                content_draft_id=sample_draft.id,
                platform="instagram",
                metric_name=name,
                metric_value=value,
                metric_date=date(2026, 2, 28),
                is_algorithm_dependent=(name in ("reach",)),
                period="day",
            )
            db_session.add(metric)
        db_session.flush()

        attributed = attribute_outcomes(db_session, sample_draft.id)
        assert all(t.actual_outcome is not None for t in attributed)
        assert attributed[0].actual_outcome["engagement_rate"] == 0.045

        # 3. EVALUATE: Compute quality scores
        period_start = date(2026, 1, 1)
        period_end = date(2026, 12, 31)
        quality_scores = evaluate_decision_quality_batch(
            db_session, sample_client.id, period_start, period_end
        )
        assert len(quality_scores) >= 1
        for qs in quality_scores:
            assert 0.0 <= qs.avg_quality_score <= 1.0

        # 4. FEEDBACK: Get decision quality context for next generation
        context = get_decision_quality_context(db_session, sample_client.id)
        assert "decision_quality" in context
        assert "guidance" in context
        assert len(context["guidance"]) > 0
