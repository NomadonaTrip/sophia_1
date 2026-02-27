"""Cross-portfolio algorithm change detection and adaptation protocol.

Detects platform algorithm shifts by computing cross-client engagement
z-scores using median absolute deviation. Requires minimum 3 clients on
the same platform. Cross-references with industry news for higher confidence.
Proposes gradual 20-30% content shift with full decision trail logging.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import numpy as np
from scipy.stats import median_abs_deviation
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def detect_algorithm_shift(
    engagement_deltas: dict[int, float],
    threshold: float = 2.0,
    min_affected_ratio: float = 0.6,
) -> dict | None:
    """Detect algorithm shift via cross-client engagement z-scores.

    When multiple clients see similar engagement changes simultaneously,
    it's likely an algorithm shift rather than content/audience issue.

    Args:
        engagement_deltas: Dict of client_id -> percentage change in
            engagement rate (week-over-week). Positive = increase.
        threshold: Modified z-score threshold for identifying uniform shift.
            Clients within this threshold are considered part of the shift.
        min_affected_ratio: Minimum ratio of affected clients to trigger
            algorithm shift detection.

    Returns:
        Dict with detection results, or None if no shift detected.
        Keys: detected, direction, magnitude_pct, affected_client_count,
        total_clients, confidence.
    """
    if len(engagement_deltas) < 3:
        return None

    values = np.array(list(engagement_deltas.values()))
    median_val = float(np.median(values))

    # Compute MAD (median absolute deviation)
    mad = float(median_abs_deviation(values, scale=1.0))

    # MAD of zero means all values are identical -- no anomaly to detect
    if mad == 0.0:
        return None

    # Modified z-scores: 0.6745 * (values - median) / mad
    z_scores = 0.6745 * (values - median_val) / mad

    # Clients within threshold are part of uniform shift
    affected_mask = np.abs(z_scores) <= threshold
    affected_count = int(np.sum(affected_mask))
    total_clients = len(values)
    affected_ratio = affected_count / total_clients

    # Must have sufficient ratio AND meaningful magnitude
    if affected_ratio < min_affected_ratio or abs(median_val) <= 0.1:
        return None

    # Determine direction
    direction = "decline" if median_val < 0 else "increase"

    # Confidence based on ratio and consistency
    if affected_ratio >= 0.8 and abs(median_val) > 0.2:
        confidence = "high"
    elif affected_ratio >= 0.6:
        confidence = "medium"
    else:
        confidence = "medium"

    return {
        "detected": True,
        "direction": direction,
        "magnitude_pct": round(float(median_val), 4),
        "affected_client_count": affected_count,
        "total_clients": total_clients,
        "confidence": confidence,
    }


def analyze_shift_nature(
    db: Session, platform: str, shift_data: dict
) -> dict:
    """Analyze the nature of a detected algorithm shift.

    Cross-references detected anomaly with industry news about platform
    changes. Classifies shift as reach-related, engagement-related, or both.

    Args:
        db: SQLAlchemy session.
        platform: Platform name (e.g., 'facebook', 'instagram').
        shift_data: Output from detect_algorithm_shift().

    Returns:
        Dict with shift analysis: platform, shift_type, industry_corroboration,
        corroborating_sources, confidence.
    """
    from sophia.research.models import FindingType, ResearchFinding

    # Query recent INDUSTRY findings mentioning the platform
    findings = (
        db.query(ResearchFinding)
        .filter(
            ResearchFinding.finding_type == FindingType.INDUSTRY,
        )
        .order_by(ResearchFinding.created_at.desc())
        .limit(20)
        .all()
    )

    # Look for corroborating industry news
    platform_lower = platform.lower()
    corroborating_sources: list[str] = []
    mentions_reach = False
    mentions_engagement = False

    algorithm_keywords = ["algorithm", "update", "change", "rollout", "ranking", "feed"]

    for finding in findings:
        text = f"{finding.topic} {finding.summary}".lower()
        if platform_lower in text and any(kw in text for kw in algorithm_keywords):
            source_name = finding.source_name or finding.source_url or "unknown"
            corroborating_sources.append(source_name)

            if any(kw in text for kw in ["reach", "impression", "visibility", "distribution"]):
                mentions_reach = True
            if any(kw in text for kw in ["engagement", "likes", "comments", "shares", "interaction"]):
                mentions_engagement = True

    industry_corroboration = len(corroborating_sources) > 0

    # Classify shift type
    if mentions_reach and mentions_engagement:
        shift_type = "both"
    elif mentions_reach:
        shift_type = "reach"
    elif mentions_engagement:
        shift_type = "engagement"
    else:
        # Infer from shift data direction
        shift_type = "engagement"

    # Confidence calculation
    if industry_corroboration and shift_data.get("confidence") == "high":
        confidence = "high"
    elif industry_corroboration:
        confidence = "medium"
    elif shift_data.get("confidence") == "high":
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "platform": platform,
        "shift_type": shift_type,
        "industry_corroboration": industry_corroboration,
        "corroborating_sources": corroborating_sources,
        "confidence": confidence,
    }


def propose_adaptation(
    db: Session,
    platform: str,
    shift_data: dict,
    shift_nature: dict,
) -> dict:
    """Generate gradual adaptation proposal for algorithm shift.

    Proposes 20-30% content approach shift. Experiments are recommended,
    not auto-triggered -- operator approves which to run. Per-client
    content adjustments remain personalized.

    Args:
        db: SQLAlchemy session.
        platform: Platform name.
        shift_data: Output from detect_algorithm_shift().
        shift_nature: Output from analyze_shift_nature().

    Returns:
        Structured adaptation proposal with hypothesis, duration,
        success metric, and rollback plan.
    """
    direction = shift_data.get("direction", "decline")
    magnitude = abs(shift_data.get("magnitude_pct", 0))
    shift_type = shift_nature.get("shift_type", "engagement")

    # Determine content shift percentage (20-30% based on magnitude)
    if magnitude > 0.3:
        shift_pct = 30
    elif magnitude > 0.2:
        shift_pct = 25
    else:
        shift_pct = 20

    # Build recommendations based on shift type
    if shift_type == "reach":
        increase_types = ["video/reels", "carousel posts", "stories"]
        decrease_types = ["static image posts", "text-only posts"]
        hypothesis = (
            f"Platform {platform} has shifted reach distribution. "
            f"Increasing video/interactive content by {shift_pct}% should "
            f"restore organic reach within 1-2 weeks."
        )
    elif shift_type == "engagement":
        increase_types = ["conversation starters", "polls/questions", "user-generated content"]
        decrease_types = ["promotional content", "link-heavy posts"]
        hypothesis = (
            f"Platform {platform} engagement algorithm has changed. "
            f"Shifting {shift_pct}% of content toward conversation-driven "
            f"formats should recover engagement rates within 1-2 weeks."
        )
    else:  # both
        increase_types = ["video/reels", "interactive content", "conversation starters"]
        decrease_types = ["static promotional posts", "link-heavy content"]
        hypothesis = (
            f"Platform {platform} has undergone broad algorithm changes "
            f"affecting both reach and engagement. A {shift_pct}% shift "
            f"toward video and interactive content should improve both "
            f"metrics within 2 weeks."
        )

    success_metric = (
        f"Engagement rate recovers to within 10% of pre-shift average "
        f"within the evaluation period"
    )

    rollback_plan = (
        f"If no improvement after evaluation period, revert to previous "
        f"content mix. Document findings as 'algorithm shift - adaptation "
        f"unsuccessful' for future reference."
    )

    return {
        "platform": platform,
        "hypothesis": hypothesis,
        "shift_percentage": shift_pct,
        "increase_content_types": increase_types,
        "decrease_content_types": decrease_types,
        "duration_days": 14,
        "success_metric": success_metric,
        "rollback_plan": rollback_plan,
        "requires_operator_approval": True,
        "shift_data_summary": {
            "direction": direction,
            "magnitude_pct": shift_data.get("magnitude_pct"),
            "affected_clients": shift_data.get("affected_client_count"),
            "total_clients": shift_data.get("total_clients"),
        },
    }


def log_algorithm_event(
    db: Session,
    platform: str,
    shift_data: dict,
    shift_nature: dict,
    adaptation: dict,
    client_ids: list[int] | None = None,
) -> list:
    """Log algorithm shift event with full decision trail.

    Creates PlatformIntelligence records with category 'required_to_play'
    (algorithm compliance is required) for each affected client.
    Write-through syncs to LanceDB.

    Args:
        db: SQLAlchemy session.
        platform: Platform name.
        shift_data: Output from detect_algorithm_shift().
        shift_nature: Output from analyze_shift_nature().
        adaptation: Output from propose_adaptation().
        client_ids: List of affected client IDs. If None, queries all
            active clients from the database.

    Returns:
        List of created PlatformIntelligence records.
    """
    from sophia.research.models import PlatformIntelligence

    now = datetime.now(timezone.utc)

    insight = (
        f"Algorithm shift detected: {shift_data.get('direction', 'unknown')} "
        f"of {abs(shift_data.get('magnitude_pct', 0)) * 100:.1f}% "
        f"across {shift_data.get('affected_client_count', 0)}/{shift_data.get('total_clients', 0)} clients. "
        f"Type: {shift_nature.get('shift_type', 'unknown')}. "
        f"Industry corroboration: {shift_nature.get('industry_corroboration', False)}."
    )

    evidence = {
        "shift_data": shift_data,
        "shift_nature": shift_nature,
        "adaptation_proposed": adaptation,
        "detected_at": now.isoformat(),
    }

    # Determine affected client IDs
    if client_ids is None:
        from sophia.intelligence.models import Client

        clients = (
            db.query(Client)
            .filter(Client.is_archived == False)  # noqa: E712
            .all()
        )
        client_ids = [c.id for c in clients]

    records = []
    for cid in client_ids:
        record = PlatformIntelligence(
            client_id=cid,
            platform=platform,
            category="required_to_play",
            insight=insight,
            evidence=evidence,
            effective_date=now,
            is_active=1,
        )
        db.add(record)
        records.append(record)

    db.commit()

    for record in records:
        db.refresh(record)

    logger.info(
        "Logged algorithm event for platform=%s across %d clients: %s",
        platform,
        len(records),
        insight[:100],
    )

    # Write-through sync to LanceDB (fire-and-forget pattern)
    for record in records:
        try:
            import asyncio

            from sophia.semantic.sync import sync_to_lance

            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(
                    sync_to_lance(
                        record_type="platform_intelligence",
                        record_id=record.id,
                        text=f"{platform} required_to_play: {insight}",
                        metadata={
                            "client_id": record.client_id,
                            "domain": platform,
                            "created_at": now.isoformat(),
                        },
                    )
                )
            else:
                loop.run_until_complete(
                    sync_to_lance(
                        record_type="platform_intelligence",
                        record_id=record.id,
                        text=f"{platform} required_to_play: {insight}",
                        metadata={
                            "client_id": record.client_id,
                            "domain": platform,
                            "created_at": now.isoformat(),
                        },
                    )
                )
        except Exception:
            logger.exception(
                "Write-through sync failed for algorithm event record_id=%d",
                record.id,
            )

    return records
