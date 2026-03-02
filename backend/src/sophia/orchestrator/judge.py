"""Multi-signal confidence evaluation for content drafts.

The judge evaluates each draft across 4 independent signals: voice
confidence, gate pass rate, content risk, and historical approval rate.
All four signals must pass for auto-approval (conservative AND logic).
Low-confidence drafts are flagged with human-readable rationale.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Risk level ordering for comparison
_RISK_LEVELS = {"safe": 0, "sensitive": 1, "risky": 2}

# Composite score weights
_WEIGHT_VOICE = 0.3
_WEIGHT_GATES = 0.3
_WEIGHT_APPROVAL = 0.2
_WEIGHT_RISK = 0.2

# Risk to numeric mapping for composite score
_RISK_SCORE = {"safe": 1.0, "sensitive": 0.3, "risky": 0.0}


@dataclass
class DraftJudgment:
    """Result of multi-signal confidence evaluation for a content draft."""

    draft_id: int
    voice_confidence: float  # 0.0-1.0 (from draft.voice_confidence_pct / 100)
    gate_pass_rate: float  # 0.0-1.0 (passed gates / total gates)
    content_risk: str  # "safe" | "sensitive" | "risky"
    historical_approval_rate: float  # from observation
    auto_approve: bool  # final decision
    rationale: str  # human-readable explanation
    confidence_score: float  # composite 0.0-1.0
    signals: dict = field(default_factory=dict)  # all raw signal values


def _extract_voice_confidence(draft) -> float:
    """Extract voice confidence from draft, converting pct to 0-1 scale."""
    pct = getattr(draft, "voice_confidence_pct", None)
    if pct is None:
        return 0.0
    return float(pct) / 100.0


def _compute_gate_pass_rate(gate_report: Optional[dict]) -> float:
    """Compute gate pass rate from gate_report JSON.

    Counts gates with status "passed" or "passed_with_fix" / total gates.
    Returns 0.0 if gate_report is None or empty.
    """
    if not gate_report:
        return 0.0

    gates = gate_report.get("gates", gate_report.get("results", []))

    # Handle dict-style gate reports (gate_name -> result)
    if isinstance(gates, dict):
        total = len(gates)
        if total == 0:
            return 0.0
        passed = sum(
            1
            for g in gates.values()
            if isinstance(g, dict) and g.get("status") in ("passed", "passed_with_fix")
        )
        return passed / total

    # Handle list-style gate reports
    if isinstance(gates, list):
        total = len(gates)
        if total == 0:
            return 0.0
        passed = sum(
            1
            for g in gates
            if isinstance(g, dict) and g.get("status") in ("passed", "passed_with_fix")
        )
        return passed / total

    return 0.0


def _determine_content_risk(gate_report: Optional[dict]) -> str:
    """Determine content risk from gate_report.

    - If sensitivity gate flagged anything -> "sensitive"
    - If any gate hard-failed -> "risky"
    - Otherwise -> "safe"
    """
    if not gate_report:
        return "safe"

    gates = gate_report.get("gates", gate_report.get("results", []))

    # Handle dict-style gate reports
    if isinstance(gates, dict):
        gate_items = gates.items()
        for name, result in gate_items:
            if not isinstance(result, dict):
                continue
            # Check for hard failures first
            if result.get("status") == "failed":
                return "risky"
        for name, result in gate_items:
            if not isinstance(result, dict):
                continue
            # Check sensitivity gate
            if "sensitiv" in name.lower() and result.get("status") != "passed":
                return "sensitive"
            if result.get("flagged") or result.get("sensitivity_flagged"):
                return "sensitive"
        return "safe"

    # Handle list-style gate reports
    if isinstance(gates, list):
        for gate in gates:
            if not isinstance(gate, dict):
                continue
            if gate.get("status") == "failed":
                return "risky"
        for gate in gates:
            if not isinstance(gate, dict):
                continue
            gate_name = gate.get("name", "").lower()
            if "sensitiv" in gate_name and gate.get("status") != "passed":
                return "sensitive"
            if gate.get("flagged") or gate.get("sensitivity_flagged"):
                return "sensitive"
        return "safe"

    return "safe"


def evaluate_draft_confidence(
    db: Session,
    draft,
    observation,
    config,
) -> DraftJudgment:
    """Evaluate a content draft across 4 independent signals.

    All four signals must pass for auto-approval (AND logic):
    1. voice_confidence >= config.min_voice_confidence
    2. gate_pass_rate == 1.0 if require_all_gates_pass (else >= 0.8)
    3. content_risk <= config.max_content_risk
    4. historical_approval_rate >= config.min_historical_approval_rate

    Args:
        db: SQLAlchemy session (unused currently, reserved for future queries)
        draft: ContentDraft instance with voice_confidence_pct and gate_report
        observation: ClientObservation with approval_rate_30d
        config: AutoApprovalConfig with threshold settings

    Returns:
        DraftJudgment with auto_approve decision and human-readable rationale
    """
    draft_id = getattr(draft, "id", 0)

    # Signal 1: Voice confidence
    voice_confidence = _extract_voice_confidence(draft)

    # Signal 2: Gate pass rate
    gate_report = getattr(draft, "gate_report", None)
    gate_pass_rate = _compute_gate_pass_rate(gate_report)

    # Signal 3: Content risk
    content_risk = _determine_content_risk(gate_report)

    # Signal 4: Historical approval rate
    historical_approval_rate = getattr(observation, "approval_rate_30d", 0.0)

    # Composite confidence score (weighted average)
    risk_score = _RISK_SCORE.get(content_risk, 0.0)
    confidence_score = (
        _WEIGHT_VOICE * voice_confidence
        + _WEIGHT_GATES * gate_pass_rate
        + _WEIGHT_APPROVAL * historical_approval_rate
        + _WEIGHT_RISK * risk_score
    )

    # AND logic: ALL four must pass
    passes = []
    failures = []

    # Check 1: Voice confidence
    min_voice = getattr(config, "min_voice_confidence", 0.75)
    if voice_confidence >= min_voice:
        passes.append(f"voice {voice_confidence:.2f} (>= {min_voice:.2f})")
    else:
        failures.append(
            f"voice confidence {voice_confidence:.2f} < {min_voice:.2f} threshold"
        )

    # Check 2: Gate pass rate
    require_all = getattr(config, "require_all_gates_pass", True)
    if require_all:
        if gate_pass_rate == 1.0:
            passes.append("all gates passed")
        else:
            failures.append(
                f"gate pass rate {gate_pass_rate:.2f} < 1.0 (all gates required)"
            )
    else:
        if gate_pass_rate >= 0.8:
            passes.append(f"gate pass rate {gate_pass_rate:.2f} (>= 0.80)")
        else:
            failures.append(
                f"gate pass rate {gate_pass_rate:.2f} < 0.80 threshold"
            )

    # Check 3: Content risk
    max_risk = getattr(config, "max_content_risk", "safe")
    max_risk_level = _RISK_LEVELS.get(max_risk, 0)
    current_risk_level = _RISK_LEVELS.get(content_risk, 2)
    if current_risk_level <= max_risk_level:
        passes.append(f"{content_risk} content")
    else:
        failures.append(
            f"content risk '{content_risk}' exceeds '{max_risk}' limit"
        )

    # Check 4: Historical approval rate
    min_approval = getattr(config, "min_historical_approval_rate", 0.80)
    if historical_approval_rate >= min_approval:
        passes.append(f"{historical_approval_rate:.0%} approval rate")
    else:
        failures.append(
            f"historical approval rate {historical_approval_rate:.0%} "
            f"< {min_approval:.0%} threshold"
        )

    # Decision: AND logic
    auto_approve = len(failures) == 0

    # Build rationale
    if auto_approve:
        rationale = "Auto-approved: " + ", ".join(passes)
    else:
        rationale = "Flagged for review: " + "; ".join(failures)

    # Pack all signal values for audit trail
    signals = {
        "voice_confidence": voice_confidence,
        "gate_pass_rate": gate_pass_rate,
        "content_risk": content_risk,
        "historical_approval_rate": historical_approval_rate,
        "confidence_score": confidence_score,
        "passes": passes,
        "failures": failures,
    }

    return DraftJudgment(
        draft_id=draft_id,
        voice_confidence=voice_confidence,
        gate_pass_rate=gate_pass_rate,
        content_risk=content_risk,
        historical_approval_rate=historical_approval_rate,
        auto_approve=auto_approve,
        rationale=rationale,
        confidence_score=confidence_score,
        signals=signals,
    )
