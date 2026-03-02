"""Client state observer for the Editor Agent's daily decision-making.

Gathers signals from posting history, engagement trends, research
freshness, anomaly detection, and approval rates to produce a
ClientObservation. Uses lazy imports for all external services with
safe defaults when data sources are unavailable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class ClientObservation:
    """Aggregated client state signals for the Editor Agent."""

    client_id: int
    client_name: str
    last_post_date: Optional[datetime]  # most recent published content
    days_since_last_post: int
    pending_approvals: int  # content waiting for operator review
    recent_engagement_trend: str  # "improving", "stable", "declining"
    research_freshness_hours: Optional[float]  # hours since last finding
    needs_research: bool  # True if stale (>24h) or no findings
    active_anomalies: int  # from analytics anomaly detection
    approval_rate_30d: float  # operator approval rate over last 30 days
    completed_cycles: int  # total cycles run for this client


def _compute_engagement_trend(db: Session, client_id: int) -> str:
    """Compute engagement trend from last 4 KPISnapshot records.

    Returns "improving" if slope is positive, "declining" if negative,
    or "stable" if fewer than 4 snapshots or near-zero slope.
    """
    try:
        from sophia.analytics.models import KPISnapshot
    except ImportError:
        return "stable"

    snapshots = (
        db.query(KPISnapshot.engagement_rate)
        .filter(
            and_(
                KPISnapshot.client_id == client_id,
                KPISnapshot.engagement_rate.isnot(None),
            )
        )
        .order_by(KPISnapshot.id.desc())
        .limit(4)
        .all()
    )

    if len(snapshots) < 4:
        return "stable"

    # Reverse to chronological order (oldest first)
    rates = [s.engagement_rate for s in reversed(snapshots)]

    # Simple slope: compare average of last 2 vs first 2
    early_avg = (rates[0] + rates[1]) / 2
    recent_avg = (rates[2] + rates[3]) / 2

    diff = recent_avg - early_avg
    # Threshold: 0.5 percentage points
    if diff > 0.5:
        return "improving"
    elif diff < -0.5:
        return "declining"
    return "stable"


def _compute_research_freshness(
    db: Session, client_id: int
) -> Optional[float]:
    """Return hours since most recent ResearchFinding, or None if none exist."""
    try:
        from sophia.research.models import ResearchFinding
    except ImportError:
        return None

    latest = (
        db.query(ResearchFinding.created_at)
        .filter(ResearchFinding.client_id == client_id)
        .order_by(ResearchFinding.id.desc())
        .first()
    )

    if latest is None or latest.created_at is None:
        return None

    created = latest.created_at
    now = datetime.now(timezone.utc)
    # Handle naive datetimes (SQLite stores naive)
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)

    delta = now - created
    return delta.total_seconds() / 3600.0


def _count_active_anomalies(db: Session, client_id: int) -> int:
    """Count active anomalies via analytics module. Returns 0 if unavailable."""
    try:
        from sophia.analytics.anomaly import detect_client_anomalies

        anomalies = detect_client_anomalies(db, client_id)
        return len(anomalies) if anomalies else 0
    except (ImportError, Exception) as exc:
        logger.debug("Anomaly detection unavailable: %s", exc)
        return 0


def _compute_approval_rate_30d(db: Session, client_id: int) -> float:
    """Compute approval rate (approved / (approved + rejected)) over 30 days."""
    try:
        from sophia.content.models import ContentDraft
    except ImportError:
        return 0.0

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now - timedelta(days=30)

    counts = (
        db.query(
            ContentDraft.status,
            func.count(ContentDraft.id),
        )
        .filter(
            and_(
                ContentDraft.client_id == client_id,
                ContentDraft.status.in_(["approved", "rejected", "published"]),
                ContentDraft.created_at >= cutoff,
            )
        )
        .group_by(ContentDraft.status)
        .all()
    )

    approved = 0
    rejected = 0
    for status, count in counts:
        if status in ("approved", "published"):
            approved += count
        elif status == "rejected":
            rejected += count

    total = approved + rejected
    if total == 0:
        return 0.0
    return approved / total


def observe_client_state(
    db: Session, client_id: int
) -> ClientObservation:
    """Gather client state signals from all available data sources.

    Aggregates signals from 6 sources: posting history, engagement trends,
    research freshness, anomaly detection, approval rates, and cycle count.
    Gracefully degrades when data sources are unavailable.
    """
    # Load client
    try:
        from sophia.intelligence.service import ClientService

        client = ClientService.get_client(db, client_id)
    except ImportError:
        from sophia.intelligence.models import Client

        client = db.get(Client, client_id)

    if client is None:
        raise ValueError(f"Client {client_id} not found")

    client_name = client.name

    # Most recent published post
    try:
        from sophia.content.models import ContentDraft
    except ImportError:
        ContentDraft = None  # type: ignore[assignment, misc]

    last_post_date: Optional[datetime] = None
    days_since_last_post = 9999
    pending_approvals = 0

    if ContentDraft is not None:
        latest_published = (
            db.query(ContentDraft.created_at)
            .filter(
                and_(
                    ContentDraft.client_id == client_id,
                    ContentDraft.status == "published",
                )
            )
            .order_by(ContentDraft.created_at.desc())
            .first()
        )

        if latest_published and latest_published.created_at:
            last_post_date = latest_published.created_at
            now = datetime.now(timezone.utc)
            created = last_post_date
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            delta = now - created
            days_since_last_post = delta.days

        # Count pending approvals
        pending_approvals = (
            db.query(func.count(ContentDraft.id))
            .filter(
                and_(
                    ContentDraft.client_id == client_id,
                    ContentDraft.status.in_(["pending_review", "in_review"]),
                )
            )
            .scalar()
            or 0
        )

    # Engagement trend
    recent_engagement_trend = _compute_engagement_trend(db, client_id)

    # Research freshness
    research_freshness_hours = _compute_research_freshness(db, client_id)
    needs_research = (
        research_freshness_hours is None or research_freshness_hours > 24.0
    )

    # Active anomalies
    active_anomalies = _count_active_anomalies(db, client_id)

    # Approval rate over last 30 days
    approval_rate_30d = _compute_approval_rate_30d(db, client_id)

    # Completed cycles from AutoApprovalConfig
    try:
        from sophia.orchestrator.models import AutoApprovalConfig

        config = (
            db.query(AutoApprovalConfig)
            .filter(AutoApprovalConfig.client_id == client_id)
            .first()
        )
        completed_cycles = config.completed_cycles if config else 0
    except ImportError:
        completed_cycles = 0

    return ClientObservation(
        client_id=client_id,
        client_name=client_name,
        last_post_date=last_post_date,
        days_since_last_post=days_since_last_post,
        pending_approvals=pending_approvals,
        recent_engagement_trend=recent_engagement_trend,
        research_freshness_hours=research_freshness_hours,
        needs_research=needs_research,
        active_anomalies=active_anomalies,
        approval_rate_30d=approval_rate_30d,
        completed_cycles=completed_cycles,
    )
