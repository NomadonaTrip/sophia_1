"""Conversion funnel tracking and CAC/CLV computation.

Tracks engagement-to-inquiry conversion pathways through funnel stages:
utm_click -> save -> follow -> dm -> inquiry -> conversion.

All functions take a SQLAlchemy session as first arg for testability
via transaction rollback.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from sophia.analytics.models import ConversionEvent

logger = logging.getLogger(__name__)

# Allowed funnel event types in order
FUNNEL_STAGES = [
    "utm_click",
    "save",
    "follow",
    "dm",
    "inquiry",
    "conversion",
]


def log_conversion_event(
    db: Session,
    client_id: int,
    event_type: str,
    source: str,
    details: Optional[dict] = None,
    content_draft_id: Optional[int] = None,
    revenue_amount: Optional[float] = None,
) -> ConversionEvent:
    """Create and persist a ConversionEvent.

    Validates event_type is in the allowed funnel stages.

    Args:
        db: SQLAlchemy session.
        client_id: Client this event belongs to.
        event_type: One of FUNNEL_STAGES.
        source: Where the event was detected ("api", "operator_reported", etc.).
        details: Optional metadata dict.
        content_draft_id: Optional link to originating content.
        revenue_amount: Optional revenue for conversion events.

    Returns:
        Created ConversionEvent.

    Raises:
        ValueError: If event_type is not in FUNNEL_STAGES.
    """
    if event_type not in FUNNEL_STAGES:
        raise ValueError(
            f"Invalid event_type '{event_type}'. "
            f"Must be one of: {', '.join(FUNNEL_STAGES)}"
        )

    event = ConversionEvent(
        client_id=client_id,
        content_draft_id=content_draft_id,
        event_type=event_type,
        source=source,
        event_date=date.today(),
        details=details,
        revenue_amount=revenue_amount,
    )
    db.add(event)
    db.flush()

    logger.info(
        "Logged conversion event: client=%d type=%s source=%s",
        client_id,
        event_type,
        source,
    )

    return event


def compute_funnel_metrics(
    db: Session, client_id: int, start_date: date, end_date: date
) -> dict:
    """Compute conversion funnel metrics for a client in a date range.

    Counts events per funnel stage, computes stage-to-stage conversion
    rates, and identifies which content drafts appear most in funnel events.

    Args:
        db: SQLAlchemy session.
        client_id: Client to analyze.
        start_date: Start of date range (inclusive).
        end_date: End of date range (inclusive).

    Returns:
        Dict with stage_counts, conversion_rates, and top_content_attributions.
    """
    events = (
        db.query(ConversionEvent)
        .filter(
            ConversionEvent.client_id == client_id,
            ConversionEvent.event_date >= start_date,
            ConversionEvent.event_date <= end_date,
        )
        .all()
    )

    # Count by stage
    stage_counts: dict[str, int] = {}
    for stage in FUNNEL_STAGES:
        stage_counts[stage] = sum(
            1 for e in events if e.event_type == stage
        )

    # Stage-to-stage conversion rates
    conversion_rates: dict[str, float] = {}
    for i in range(len(FUNNEL_STAGES) - 1):
        current_stage = FUNNEL_STAGES[i]
        next_stage = FUNNEL_STAGES[i + 1]
        current_count = stage_counts[current_stage]
        next_count = stage_counts[next_stage]
        key = f"{current_stage}_to_{next_stage}"
        if current_count > 0:
            conversion_rates[key] = round(
                next_count / current_count * 100, 2
            )
        else:
            conversion_rates[key] = 0.0

    # Content attribution: which draft IDs appear most
    draft_counter: Counter = Counter()
    for e in events:
        if e.content_draft_id is not None:
            draft_counter[e.content_draft_id] += 1

    top_attributions = [
        {"content_draft_id": draft_id, "event_count": count}
        for draft_id, count in draft_counter.most_common(10)
    ]

    return {
        "stage_counts": stage_counts,
        "conversion_rates": conversion_rates,
        "top_content_attributions": top_attributions,
        "total_events": len(events),
    }


def compute_cac(
    db: Session, client_id: int, period_months: int = 3
) -> Optional[dict]:
    """Compute Customer Acquisition Cost and Customer Lifetime Value.

    Only returns data when actual revenue ConversionEvents exist.
    Returns None when no revenue data is available (no made-up numbers).

    Args:
        db: SQLAlchemy session.
        client_id: Client to compute CAC for.
        period_months: Number of months to look back.

    Returns:
        Dict with total_revenue, conversion_count, cac, clv,
        or None if no revenue data exists.
    """
    cutoff = date.today() - timedelta(days=period_months * 30)

    # Get conversion events with revenue
    revenue_events = (
        db.query(ConversionEvent)
        .filter(
            ConversionEvent.client_id == client_id,
            ConversionEvent.event_type == "conversion",
            ConversionEvent.revenue_amount.isnot(None),
            ConversionEvent.event_date >= cutoff,
        )
        .all()
    )

    if not revenue_events:
        return None

    total_revenue = sum(e.revenue_amount for e in revenue_events)
    conversion_count = len(revenue_events)

    # Unique customers approximated by unique content_draft_ids or event count
    unique_sources = len(
        set(
            e.content_draft_id
            for e in revenue_events
            if e.content_draft_id is not None
        )
    ) or conversion_count

    clv = round(total_revenue / unique_sources, 2) if unique_sources > 0 else 0

    # CAC: service cost / conversions (placeholder: use revenue / conversions as proxy)
    # Real CAC requires client service cost data which may not be available
    cac = round(total_revenue / conversion_count, 2) if conversion_count > 0 else 0

    return {
        "total_revenue": round(total_revenue, 2),
        "conversion_count": conversion_count,
        "cac": cac,
        "clv": clv,
        "period_months": period_months,
    }
