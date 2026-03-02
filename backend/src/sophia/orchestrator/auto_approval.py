"""Auto-approval decision logic with burn-in and suspension.

Orchestrates the approval decision by checking:
1. Whether auto-approval is enabled for the client
2. Whether the burn-in period has been completed
3. Whether auto-approval is suspended due to false positives
4. If all checks pass, delegates to the judge for signal evaluation

Conservative by default: any doubt results in human review.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from sophia.orchestrator.judge import DraftJudgment, evaluate_draft_confidence
from sophia.orchestrator.models import AutoApprovalConfig, SpecialistAgent

logger = logging.getLogger(__name__)


def _get_or_create_config(
    db: Session, client_id: int
) -> AutoApprovalConfig:
    """Load AutoApprovalConfig for client, creating with defaults if none exists."""
    config = (
        db.query(AutoApprovalConfig)
        .filter(AutoApprovalConfig.client_id == client_id)
        .first()
    )
    if config is not None:
        return config

    config = AutoApprovalConfig(client_id=client_id)
    db.add(config)
    db.flush()
    return config


def _is_suspended(config: AutoApprovalConfig, db: Session) -> bool:
    """Check if auto-approval is suspended due to false positives.

    Suspended when 3+ false positives occurred within the last 7 days.
    Checks the specialist agent's false_positive_count and window_start.
    """
    specialist = (
        db.query(SpecialistAgent)
        .filter(
            SpecialistAgent.client_id == config.client_id,
            SpecialistAgent.is_active.is_(True),
        )
        .first()
    )
    if specialist is None:
        return False

    if specialist.false_positive_count < 3:
        return False

    if specialist.false_positive_window_start is None:
        return False

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    window_cutoff = now - timedelta(days=7)

    return specialist.false_positive_window_start >= window_cutoff


def check_burn_in_status(db: Session, client_id: int) -> dict:
    """Check whether a client is still in the auto-approval burn-in period.

    Returns:
        dict with keys: in_burn_in, cycles_remaining, enabled, suspended
    """
    config = _get_or_create_config(db, client_id)
    in_burn_in = config.completed_cycles < config.burn_in_cycles
    cycles_remaining = max(0, config.burn_in_cycles - config.completed_cycles)
    suspended = _is_suspended(config, db)

    return {
        "in_burn_in": in_burn_in,
        "cycles_remaining": cycles_remaining,
        "enabled": config.enabled,
        "suspended": suspended,
    }


def should_auto_approve(
    db: Session, draft, observation
) -> DraftJudgment:
    """Determine whether a draft should be auto-approved.

    Applies pre-checks before delegating to the judge:
    1. Is auto-approval enabled for this client?
    2. Has the burn-in period been completed?
    3. Is auto-approval suspended due to false positives?

    Always returns a DraftJudgment with full signal data regardless
    of whether auto-approval was blocked by pre-checks.

    Args:
        db: SQLAlchemy session
        draft: ContentDraft instance
        observation: ClientObservation from observer
    """
    client_id = getattr(draft, "client_id", getattr(observation, "client_id", 0))
    config = _get_or_create_config(db, client_id)

    draft_id = getattr(draft, "id", 0)

    # Pre-check 1: Is auto-approval enabled?
    if not config.enabled:
        return DraftJudgment(
            draft_id=draft_id,
            voice_confidence=0.0,
            gate_pass_rate=0.0,
            content_risk="safe",
            historical_approval_rate=getattr(observation, "approval_rate_30d", 0.0),
            auto_approve=False,
            rationale="Auto-approval disabled for this client",
            confidence_score=0.0,
            signals={
                "blocked_by": "disabled",
                "enabled": False,
            },
        )

    # Pre-check 2: Burn-in period
    if config.completed_cycles < config.burn_in_cycles:
        remaining = config.burn_in_cycles - config.completed_cycles
        return DraftJudgment(
            draft_id=draft_id,
            voice_confidence=0.0,
            gate_pass_rate=0.0,
            content_risk="safe",
            historical_approval_rate=getattr(observation, "approval_rate_30d", 0.0),
            auto_approve=False,
            rationale=(
                f"Burn-in period: {config.completed_cycles}/{config.burn_in_cycles} "
                f"cycles completed ({remaining} remaining)"
            ),
            confidence_score=0.0,
            signals={
                "blocked_by": "burn_in",
                "completed_cycles": config.completed_cycles,
                "burn_in_cycles": config.burn_in_cycles,
                "cycles_remaining": remaining,
            },
        )

    # Pre-check 3: Suspension
    if _is_suspended(config, db):
        specialist = (
            db.query(SpecialistAgent)
            .filter(
                SpecialistAgent.client_id == client_id,
                SpecialistAgent.is_active.is_(True),
            )
            .first()
        )
        fp_count = specialist.false_positive_count if specialist else 0
        return DraftJudgment(
            draft_id=draft_id,
            voice_confidence=0.0,
            gate_pass_rate=0.0,
            content_risk="safe",
            historical_approval_rate=getattr(observation, "approval_rate_30d", 0.0),
            auto_approve=False,
            rationale=(
                f"Auto-approval suspended: {fp_count} false positives in 7 days"
            ),
            confidence_score=0.0,
            signals={
                "blocked_by": "suspension",
                "false_positive_count": fp_count,
            },
        )

    # All pre-checks passed: evaluate via judge
    return evaluate_draft_confidence(db, draft, observation, config)


def record_auto_approval_outcome(
    db: Session, client_id: int, draft_id: int, was_correct: bool
) -> None:
    """Record the outcome of an auto-approval decision.

    If the auto-approval was incorrect (operator rejected after auto-approve),
    records a false positive on the specialist agent. Always increments
    completed_cycles on the AutoApprovalConfig.

    Args:
        db: SQLAlchemy session
        client_id: Client ID
        draft_id: ContentDraft ID (for audit trail logging)
        was_correct: True if operator confirmed, False if operator rejected
    """
    if not was_correct:
        try:
            from sophia.orchestrator.specialist import record_false_positive

            specialist = (
                db.query(SpecialistAgent)
                .filter(
                    SpecialistAgent.client_id == client_id,
                    SpecialistAgent.is_active.is_(True),
                )
                .first()
            )
            if specialist:
                record_false_positive(db, specialist.id)
                logger.warning(
                    "False positive recorded for client %d, draft %d",
                    client_id,
                    draft_id,
                )
        except ImportError:
            logger.error("Could not import specialist service for false positive recording")

    # Increment completed_cycles
    config = (
        db.query(AutoApprovalConfig)
        .filter(AutoApprovalConfig.client_id == client_id)
        .first()
    )
    if config:
        config.completed_cycles += 1
        db.flush()
