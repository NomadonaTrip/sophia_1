"""Decision trace pipeline: capture, attribution, quality evaluation, feedback loop.

Every content decision is traced, linked to performance outcomes, evaluated for
quality, and fed back into future generation. This is what makes Sophia genuinely
learn, not just generate.

Pipeline stages:
  capture -> attribute -> evaluate -> feedback

Decision traces are captured at each content cycle stage:
  research, angle, persona, format, voice, gate, approval, performance
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from sophia.analytics.models import (
    DecisionQualityScore,
    DecisionTrace,
    EngagementMetric,
)

logger = logging.getLogger(__name__)

# Allowed stages for decision traces
ALLOWED_STAGES = frozenset({
    "research",
    "angle",
    "persona",
    "format",
    "voice",
    "gate",
    "approval",
    "performance",
})

# Stage -> decision_type mapping for quality evaluation
STAGE_TO_DECISION_TYPE = {
    "research": "topic_selection",
    "angle": "topic_selection",
    "persona": "persona_targeting",
    "format": "format_choice",
    "voice": "voice_calibration",
    "gate": "format_choice",
    "approval": "voice_calibration",
    "performance": "timing",
}

# Quality score weights per decision_type
QUALITY_WEIGHTS: dict[str, dict[str, float]] = {
    "topic_selection": {"engagement_rate": 0.4, "save_rate": 0.3, "reach": 0.3},
    "format_choice": {"engagement_rate": 0.5, "share_rate": 0.3, "save_rate": 0.2},
    "timing": {"reach": 0.5, "engagement_rate": 0.3, "views": 0.2},
    "voice_calibration": {"approval_first_pass": 0.6, "edit_count": 0.4},
    "persona_targeting": {"engagement_rate": 0.4, "save_rate": 0.3, "share_rate": 0.3},
}

# Maximum evidence keys to store (prevent trace bloat)
MAX_EVIDENCE_KEYS = 5


# =============================================================================
# Capture functions
# =============================================================================


def capture_decision(
    db: Session,
    draft_id: int,
    client_id: int,
    stage: str,
    decision: str,
    alternatives: Optional[list[str]] = None,
    rationale: Optional[str] = None,
    evidence: Optional[dict] = None,
    confidence: Optional[float] = None,
    predicted_outcome: Optional[dict] = None,
) -> DecisionTrace:
    """Create and persist a DecisionTrace record.

    Validates stage is in allowed set. Alternatives stored as brief labels only
    (not full text, per pitfall #4 about trace bloat). Evidence capped to top 5
    key-value pairs if dict is larger.
    """
    if stage not in ALLOWED_STAGES:
        raise ValueError(
            f"Invalid stage '{stage}'. Allowed: {sorted(ALLOWED_STAGES)}"
        )

    # Cap evidence to MAX_EVIDENCE_KEYS
    capped_evidence = evidence
    if evidence and len(evidence) > MAX_EVIDENCE_KEYS:
        capped_evidence = dict(list(evidence.items())[:MAX_EVIDENCE_KEYS])

    # Store alternatives as brief labels only
    alt_data: Optional[list[str]] = None
    if alternatives:
        alt_data = [str(a)[:100] for a in alternatives]

    trace = DecisionTrace(
        content_draft_id=draft_id,
        client_id=client_id,
        stage=stage,
        decision=decision,
        alternatives_considered=alt_data,
        rationale=rationale,
        evidence=capped_evidence,
        confidence=confidence,
        predicted_outcome=predicted_outcome,
    )
    db.add(trace)
    db.flush()
    return trace


def capture_generation_decisions(
    db: Session,
    draft: Any,
    generation_context: dict,
) -> list[DecisionTrace]:
    """Convenience function called from content service after generation.

    Creates traces for: research (what research was used), angle (content angle
    chosen), persona (target persona), format (content format selected).
    Extracts info from draft fields and generation_context dict.
    """
    traces: list[DecisionTrace] = []
    draft_id = draft.id
    client_id = draft.client_id

    # Research decision
    research_ids = generation_context.get("research_ids", [])
    traces.append(capture_decision(
        db=db,
        draft_id=draft_id,
        client_id=client_id,
        stage="research",
        decision=f"Used {len(research_ids)} research sources",
        alternatives=generation_context.get("research_alternatives"),
        evidence={"research_ids": research_ids[:MAX_EVIDENCE_KEYS]},
        confidence=generation_context.get("research_confidence"),
    ))

    # Angle decision
    angle = generation_context.get("angle", getattr(draft, "content_pillar", "general"))
    traces.append(capture_decision(
        db=db,
        draft_id=draft_id,
        client_id=client_id,
        stage="angle",
        decision=f"Content angle: {angle}",
        alternatives=generation_context.get("angle_alternatives"),
        rationale=generation_context.get("angle_rationale"),
        confidence=generation_context.get("angle_confidence"),
    ))

    # Persona decision
    persona = generation_context.get("persona", "general audience")
    traces.append(capture_decision(
        db=db,
        draft_id=draft_id,
        client_id=client_id,
        stage="persona",
        decision=f"Target persona: {persona}",
        alternatives=generation_context.get("persona_alternatives"),
        confidence=generation_context.get("persona_confidence"),
    ))

    # Format decision
    content_type = getattr(draft, "content_type", "feed")
    platform = getattr(draft, "platform", "unknown")
    traces.append(capture_decision(
        db=db,
        draft_id=draft_id,
        client_id=client_id,
        stage="format",
        decision=f"Format: {content_type} on {platform}",
        alternatives=generation_context.get("format_alternatives"),
        confidence=generation_context.get("format_confidence"),
    ))

    return traces


def capture_gate_decision(
    db: Session,
    draft: Any,
    gate_report: dict,
) -> DecisionTrace:
    """Called after quality gates. Records gate outcome as a 'gate' stage trace.

    Decision = gate_status. Evidence = summary of gate scores (not full report).
    """
    gate_status = gate_report.get("status", "unknown")

    # Build evidence summary (not full report -- avoid bloat)
    results = gate_report.get("results", [])
    evidence: dict[str, Any] = {
        "status": gate_status,
        "gates_passed": sum(
            1 for r in results if r.get("status") in ("passed", "passed_with_fix")
        ),
        "gates_total": len(results),
    }
    rejected_by = gate_report.get("rejected_by")
    if rejected_by:
        evidence["rejected_by"] = rejected_by

    return capture_decision(
        db=db,
        draft_id=draft.id,
        client_id=draft.client_id,
        stage="gate",
        decision=gate_status,
        evidence=evidence,
        confidence=1.0 if gate_status == "passed" else 0.5,
    )


def capture_approval_decision(
    db: Session,
    draft_id: int,
    client_id: int,
    action: str,
    actor: str,
) -> DecisionTrace:
    """Called from approval service on each state transition.

    Records 'approval' stage with the action and actor.
    """
    return capture_decision(
        db=db,
        draft_id=draft_id,
        client_id=client_id,
        stage="approval",
        decision=action,
        evidence={"actor": actor},
        confidence=1.0,
    )


# =============================================================================
# Attribution functions
# =============================================================================


def attribute_outcomes(
    db: Session,
    content_draft_id: int,
) -> list[DecisionTrace]:
    """Called after engagement metrics are collected for a published post.

    Steps:
    a. Query EngagementMetric for this draft (by content_draft_id)
    b. Build actual_outcome dict
    c. Query all DecisionTrace for this draft_id
    d. Update actual_outcome on each trace
    e. Flush and return updated traces
    """
    # a. Query engagement metrics for this draft
    metrics = (
        db.query(EngagementMetric)
        .filter_by(content_draft_id=content_draft_id)
        .all()
    )

    if not metrics:
        # No metrics yet -- return traces unchanged
        return (
            db.query(DecisionTrace)
            .filter_by(content_draft_id=content_draft_id)
            .all()
        )

    # b. Build actual_outcome dict from metric rows
    actual_outcome: dict[str, float] = {}
    for metric in metrics:
        actual_outcome[metric.metric_name] = metric.metric_value

    # c. Query all DecisionTrace for this draft
    traces = (
        db.query(DecisionTrace)
        .filter_by(content_draft_id=content_draft_id)
        .all()
    )

    # d. Update actual_outcome on each trace
    for trace in traces:
        trace.actual_outcome = actual_outcome

    # e. Flush and return
    db.flush()
    return traces


def attribute_batch(
    db: Session,
    client_id: int,
) -> int:
    """Find all published drafts for client that have engagement metrics but
    no actual_outcome on their traces. Call attribute_outcomes for each.
    Return count of traces updated.
    """
    try:
        from sophia.content.models import ContentDraft
    except ImportError:
        return 0

    # Find draft IDs that have metrics but traces without actual_outcome
    # Subquery: drafts with engagement metrics
    drafts_with_metrics = (
        db.query(EngagementMetric.content_draft_id)
        .filter(
            EngagementMetric.client_id == client_id,
            EngagementMetric.content_draft_id.isnot(None),
        )
        .distinct()
        .subquery()
    )

    # Find traces for those drafts where actual_outcome is null
    unattributed_traces = (
        db.query(DecisionTrace.content_draft_id)
        .filter(
            DecisionTrace.client_id == client_id,
            DecisionTrace.content_draft_id.in_(
                db.query(drafts_with_metrics.c.content_draft_id)
            ),
            DecisionTrace.actual_outcome.is_(None),
        )
        .distinct()
        .all()
    )

    count = 0
    for (draft_id,) in unattributed_traces:
        traces = attribute_outcomes(db, draft_id)
        count += len([t for t in traces if t.actual_outcome is not None])

    return count


# =============================================================================
# Quality evaluation functions
# =============================================================================


def compute_decision_quality(
    predicted: dict,
    actual: dict,
    decision_type: str,
) -> float:
    """Compare predicted vs actual outcomes. Returns quality score 0.0 to 1.0.

    Quality = 1.0 - |1.0 - min(actual/predicted, 2.0)| weighted sum.
    Uses weights per decision_type.
    """
    weights = QUALITY_WEIGHTS.get(decision_type, {"engagement_rate": 1.0})

    if not predicted or not actual:
        return 0.0

    total_weight = 0.0
    weighted_score = 0.0

    for metric, weight in weights.items():
        pred_val = predicted.get(metric)
        act_val = actual.get(metric)

        if pred_val is None or act_val is None:
            continue

        pred_val = float(pred_val)
        act_val = float(act_val)

        if pred_val == 0:
            # Cannot compute ratio with 0 predicted
            continue

        ratio = min(act_val / pred_val, 2.0)
        quality = 1.0 - abs(1.0 - ratio)
        weighted_score += quality * weight
        total_weight += weight

    if total_weight == 0:
        return 0.0

    return max(0.0, min(1.0, weighted_score / total_weight))


def evaluate_decision_quality_batch(
    db: Session,
    client_id: int,
    period_start: date,
    period_end: date,
) -> list[DecisionQualityScore]:
    """Evaluate decision quality for a client over a period.

    Steps:
    a. Query DecisionTraces for client in period where actual_outcome is not null
    b. Group by stage (mapped to decision_type)
    c. For each group: compute quality scores, average them, create/update
       DecisionQualityScore record
    d. Return list of quality scores
    """
    # a. Query traces with actual outcomes in period
    traces = (
        db.query(DecisionTrace)
        .filter(
            DecisionTrace.client_id == client_id,
            DecisionTrace.actual_outcome.isnot(None),
            DecisionTrace.created_at >= period_start,
            DecisionTrace.created_at <= period_end,
        )
        .all()
    )

    # b. Group by decision_type (via stage mapping)
    groups: dict[str, list[DecisionTrace]] = {}
    for trace in traces:
        dt = STAGE_TO_DECISION_TYPE.get(trace.stage, trace.stage)
        groups.setdefault(dt, []).append(trace)

    # c. For each group, compute scores
    quality_scores: list[DecisionQualityScore] = []

    for decision_type, group_traces in groups.items():
        scores: list[float] = []
        for trace in group_traces:
            predicted = trace.predicted_outcome or {}
            actual = trace.actual_outcome or {}
            if predicted:
                score = compute_decision_quality(predicted, actual, decision_type)
                scores.append(score)

        if not scores:
            continue

        avg_score = sum(scores) / len(scores)

        # Create or update DecisionQualityScore
        existing = (
            db.query(DecisionQualityScore)
            .filter_by(
                client_id=client_id,
                decision_type=decision_type,
                period_start=period_start,
                period_end=period_end,
            )
            .first()
        )

        if existing:
            existing.sample_count = len(scores)
            existing.avg_quality_score = avg_score
            existing.scores_detail = {
                "individual_scores": scores[:20],
                "trace_count": len(group_traces),
            }
            quality_scores.append(existing)
        else:
            qs = DecisionQualityScore(
                client_id=client_id,
                decision_type=decision_type,
                period_start=period_start,
                period_end=period_end,
                sample_count=len(scores),
                avg_quality_score=avg_score,
                scores_detail={
                    "individual_scores": scores[:20],
                    "trace_count": len(group_traces),
                },
            )
            db.add(qs)
            quality_scores.append(qs)

    db.flush()
    return quality_scores


# =============================================================================
# Feedback loop function
# =============================================================================


def get_decision_quality_context(
    db: Session,
    client_id: int,
) -> dict:
    """Query most recent DecisionQualityScore records for this client.

    Returns dict suitable for injection into content generation prompt context.
    If no quality data exists (cold start), return empty dict.
    """
    # Get the most recent score per decision_type
    all_types = list(QUALITY_WEIGHTS.keys())
    context: dict[str, Any] = {}

    for dt in all_types:
        score = (
            db.query(DecisionQualityScore)
            .filter_by(client_id=client_id, decision_type=dt)
            .order_by(DecisionQualityScore.period_end.desc())
            .first()
        )
        if score:
            # Extract best-performing patterns from scores_detail
            detail = score.scores_detail or {}
            context[dt] = {
                "avg_score": score.avg_quality_score,
                "sample_count": score.sample_count,
                "best_performing": detail.get("best_performing", []),
            }

    if not context:
        return {}

    # Build guidance text
    guidance_parts: list[str] = []
    for dt, info in context.items():
        avg = info["avg_score"]
        label = dt.replace("_", " ")
        if avg is not None:
            if avg >= 0.7:
                guidance_parts.append(f"{label} quality is strong ({avg:.2f})")
            elif avg >= 0.5:
                guidance_parts.append(f"{label} quality is moderate ({avg:.2f})")
            else:
                guidance_parts.append(f"{label} quality needs improvement ({avg:.2f})")

    return {
        "decision_quality": context,
        "guidance": ". ".join(guidance_parts) + "." if guidance_parts else "",
    }
