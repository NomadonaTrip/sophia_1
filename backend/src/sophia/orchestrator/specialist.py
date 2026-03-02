"""Specialist agent CRUD and state management service.

Follows the static-method-with-Session pattern established in Phase 1.
All functions accept a SQLAlchemy Session as the first argument.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from sophia.orchestrator.models import AutoApprovalConfig, SpecialistAgent


# ---------------------------------------------------------------------------
# Pure utility
# ---------------------------------------------------------------------------


def compact_state(state_json: dict, max_entries: int = 50) -> dict:
    """Prune list values in state_json to last max_entries items.

    Pure function -- does not mutate input. Returns a new dict with all
    list values truncated to the most recent max_entries items. Non-list
    values are passed through unchanged.
    """
    compacted: dict = {}
    for key, value in state_json.items():
        if isinstance(value, list) and len(value) > max_entries:
            compacted[key] = value[-max_entries:]
        else:
            compacted[key] = value
    return compacted


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def create_specialist(
    db: Session,
    client_id: int,
    specialty: str = "general",
) -> SpecialistAgent:
    """Create a new specialist agent for a client."""
    agent = SpecialistAgent(
        client_id=client_id,
        specialty=specialty,
        state_json={},
    )
    db.add(agent)
    db.flush()
    return agent


def get_specialist(
    db: Session,
    specialist_id: int,
) -> Optional[SpecialistAgent]:
    """Get a specialist agent by ID, or None if not found."""
    return db.get(SpecialistAgent, specialist_id)


def get_or_create_specialist(
    db: Session,
    client_id: int,
    specialty: str = "general",
) -> SpecialistAgent:
    """Find an existing active specialist for the client, or create one.

    Returns the first active specialist matching client_id and specialty.
    If none exists, creates a new one.
    """
    existing = (
        db.query(SpecialistAgent)
        .filter(
            and_(
                SpecialistAgent.client_id == client_id,
                SpecialistAgent.specialty == specialty,
                SpecialistAgent.is_active.is_(True),
            )
        )
        .first()
    )
    if existing is not None:
        return existing
    return create_specialist(db, client_id, specialty)


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------


def update_specialist_state(
    db: Session,
    specialist_id: int,
    new_state: dict,
    cycle_id: int,
) -> SpecialistAgent:
    """Merge new_state into existing state_json and update cycle tracking.

    New state keys are merged at the top level. List values are extended
    (appended), then compacted to max 50 entries. Non-list values are
    overwritten.

    Uses flag_modified() for SQLAlchemy JSON mutation detection.
    """
    agent = db.get(SpecialistAgent, specialist_id)
    if agent is None:
        raise ValueError(f"Specialist agent {specialist_id} not found")

    current = dict(agent.state_json) if agent.state_json else {}

    for key, value in new_state.items():
        if isinstance(value, list) and isinstance(current.get(key), list):
            current[key] = current[key] + value
        else:
            current[key] = value

    agent.state_json = compact_state(current)
    flag_modified(agent, "state_json")

    agent.total_cycles += 1
    agent.last_cycle_id = cycle_id

    db.flush()
    return agent


def update_approval_rate(
    db: Session,
    specialist_id: int,
    was_approved: bool,
) -> SpecialistAgent:
    """Incrementally update approval_rate using EMA (alpha=0.1).

    Exponential moving average gives more weight to recent approvals
    while maintaining history.
    """
    agent = db.get(SpecialistAgent, specialist_id)
    if agent is None:
        raise ValueError(f"Specialist agent {specialist_id} not found")

    alpha = 0.1
    value = 1.0 if was_approved else 0.0
    agent.approval_rate = alpha * value + (1 - alpha) * agent.approval_rate

    db.flush()
    return agent


def record_false_positive(
    db: Session,
    specialist_id: int,
) -> SpecialistAgent:
    """Record a false positive (auto-approved but operator-rejected).

    Increments false_positive_count and sets window_start if first in
    window. If 3+ false positives within 7 days, auto-disables
    auto-approval for that client.
    """
    agent = db.get(SpecialistAgent, specialist_id)
    if agent is None:
        raise ValueError(f"Specialist agent {specialist_id} not found")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    window_cutoff = now - timedelta(days=7)

    # Reset window if expired
    if (
        agent.false_positive_window_start is not None
        and agent.false_positive_window_start < window_cutoff
    ):
        agent.false_positive_count = 0
        agent.false_positive_window_start = None

    # Set window start if first in current window
    if agent.false_positive_window_start is None:
        agent.false_positive_window_start = now

    agent.false_positive_count += 1

    # Auto-disable auto-approval on 3+ false positives in 7 days
    if agent.false_positive_count >= 3:
        config = (
            db.query(AutoApprovalConfig)
            .filter(AutoApprovalConfig.client_id == agent.client_id)
            .first()
        )
        if config is not None:
            config.enabled = False

    db.flush()
    return agent


def deactivate_specialist(
    db: Session,
    specialist_id: int,
) -> SpecialistAgent:
    """Deactivate a specialist agent (sets is_active = False)."""
    agent = db.get(SpecialistAgent, specialist_id)
    if agent is None:
        raise ValueError(f"Specialist agent {specialist_id} not found")

    agent.is_active = False
    db.flush()
    return agent
