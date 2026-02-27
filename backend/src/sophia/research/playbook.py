"""Living platform playbook management.

Maintains per-client platform intelligence profiles categorized as
'required_to_play' (table-stakes) vs 'sufficient_to_win' (differentiating).
Updates continuously from performance data and algorithm shift events.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from sophia.research.models import PlatformIntelligence

logger = logging.getLogger(__name__)


def update_playbook(
    db: Session,
    client_id: int,
    platform: str,
    insight: str,
    evidence: dict,
    category: str,
) -> PlatformIntelligence:
    """Create or update a PlatformIntelligence record in the playbook.

    Deactivates outdated insights when a new conflicting insight is added
    for the same client, platform, and category. Write-through syncs to LanceDB.

    Args:
        db: SQLAlchemy session.
        client_id: Client ID.
        platform: Platform name (e.g., 'facebook', 'instagram').
        insight: The platform intelligence insight text.
        evidence: Supporting performance data dict.
        category: 'required_to_play' or 'sufficient_to_win'.

    Returns:
        The created PlatformIntelligence record.
    """
    now = datetime.now(timezone.utc)

    # Deactivate conflicting existing insights in the same category
    # An insight conflicts if it's for the same client+platform+category
    # and covers the same topic (simple keyword overlap check)
    existing = (
        db.query(PlatformIntelligence)
        .filter(
            PlatformIntelligence.client_id == client_id,
            PlatformIntelligence.platform == platform,
            PlatformIntelligence.category == category,
            PlatformIntelligence.is_active == 1,
        )
        .all()
    )

    insight_words = set(insight.lower().split())
    for old_entry in existing:
        old_words = set(old_entry.insight.lower().split())
        overlap = len(insight_words & old_words)
        # If >40% word overlap, consider it a conflicting/updated insight
        if overlap > 0 and overlap / max(len(insight_words), 1) > 0.4:
            old_entry.is_active = 0
            logger.debug(
                "Deactivated outdated insight id=%d for client=%d platform=%s",
                old_entry.id,
                client_id,
                platform,
            )

    # Create new insight
    record = PlatformIntelligence(
        client_id=client_id,
        platform=platform,
        category=category,
        insight=insight,
        evidence=evidence,
        effective_date=now,
        is_active=1,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    # Write-through sync to LanceDB
    try:
        import asyncio

        from sophia.semantic.sync import sync_to_lance

        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(
                sync_to_lance(
                    record_type="platform_intelligence",
                    record_id=record.id,
                    text=f"{platform} {category}: {insight}",
                    metadata={
                        "client_id": client_id,
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
                    text=f"{platform} {category}: {insight}",
                    metadata={
                        "client_id": client_id,
                        "domain": platform,
                        "created_at": now.isoformat(),
                    },
                )
            )
    except Exception:
        logger.exception(
            "Write-through sync failed for playbook record_id=%d",
            record.id,
        )

    return record


def get_platform_playbook(
    db: Session, client_id: int, platform: str
) -> dict:
    """Return active platform intelligence organized by category.

    Returns a structured dict with 'required_to_play' and 'sufficient_to_win'
    lists, each containing active insights with evidence and effective dates.

    Args:
        db: SQLAlchemy session.
        client_id: Client ID.
        platform: Platform name.

    Returns:
        Dict with 'required_to_play' and 'sufficient_to_win' insight lists.
    """
    entries = (
        db.query(PlatformIntelligence)
        .filter(
            PlatformIntelligence.client_id == client_id,
            PlatformIntelligence.platform == platform,
            PlatformIntelligence.is_active == 1,
        )
        .order_by(PlatformIntelligence.effective_date.desc())
        .all()
    )

    playbook: dict[str, list[dict]] = {
        "required_to_play": [],
        "sufficient_to_win": [],
    }

    for entry in entries:
        item = {
            "id": entry.id,
            "insight": entry.insight,
            "evidence": entry.evidence,
            "effective_date": (
                entry.effective_date.isoformat()
                if entry.effective_date
                else None
            ),
        }
        category = entry.category
        if category in playbook:
            playbook[category].append(item)

    return playbook


def categorize_insight(insight: str, evidence: dict) -> str:
    """Classify a platform insight as 'required_to_play' or 'sufficient_to_win'.

    required_to_play: formatting requirements, minimum posting frequency,
        mandatory features (e.g., hashtags, alt text, specific formats).
    sufficient_to_win: optimal timing, content formats with highest engagement,
        audience targeting strategies, competitive advantages.

    Args:
        insight: The insight text to classify.
        evidence: Supporting performance data.

    Returns:
        'required_to_play' or 'sufficient_to_win'.
    """
    insight_lower = insight.lower()

    # Keywords indicating required_to_play (table-stakes)
    required_keywords = [
        "must", "required", "mandatory", "minimum", "at least",
        "format requirement", "hashtag", "alt text", "accessibility",
        "posting frequency", "minimum frequency", "compliance",
        "algorithm requirement", "penalize", "restrict", "block",
        "need to", "have to", "essential",
    ]

    # Keywords indicating sufficient_to_win (competitive advantage)
    win_keywords = [
        "optimal", "best time", "highest engagement", "outperform",
        "competitive advantage", "differentiate", "strategy",
        "audience targeting", "top performing", "above average",
        "trending", "opportunity", "growth", "boost",
    ]

    required_score = sum(1 for kw in required_keywords if kw in insight_lower)
    win_score = sum(1 for kw in win_keywords if kw in insight_lower)

    # Evidence-based boost: if evidence contains compliance/penalty data
    if evidence:
        evidence_str = str(evidence).lower()
        if any(kw in evidence_str for kw in ["penalty", "required", "compliance"]):
            required_score += 2
        if any(kw in evidence_str for kw in ["improvement", "growth", "engagement_lift"]):
            win_score += 1

    if required_score > win_score:
        return "required_to_play"
    return "sufficient_to_win"


def merge_algorithm_shift_into_playbook(
    db: Session,
    platform: str,
    shift_data: dict,
    adaptation: dict,
) -> list[PlatformIntelligence]:
    """Update playbook for ALL clients on a platform after algorithm shift.

    Creates new 'required_to_play' entries reflecting new algorithm requirements.
    Deactivates entries that conflict with new algorithm behavior.

    Args:
        db: SQLAlchemy session.
        platform: Platform name.
        shift_data: Output from detect_algorithm_shift().
        adaptation: Output from propose_adaptation().

    Returns:
        List of newly created PlatformIntelligence records.
    """
    from sophia.intelligence.models import Client

    # Get all active, non-archived clients
    clients = (
        db.query(Client)
        .filter(Client.is_archived == False)  # noqa: E712
        .all()
    )

    # Filter to clients on this platform
    platform_clients = []
    for client in clients:
        accounts = client.platform_accounts or []
        # Check if client has this platform in their accounts
        has_platform = False
        if isinstance(accounts, list):
            for acct in accounts:
                if isinstance(acct, dict) and acct.get("platform", "").lower() == platform.lower():
                    has_platform = True
                    break
                elif isinstance(acct, str) and acct.lower() == platform.lower():
                    has_platform = True
                    break

        # If no platform_accounts set, include all clients (conservative)
        if not accounts or has_platform:
            platform_clients.append(client)

    direction = shift_data.get("direction", "unknown")
    increase_types = adaptation.get("increase_content_types", [])
    decrease_types = adaptation.get("decrease_content_types", [])

    new_records = []

    for client in platform_clients:
        # Build insight from adaptation data
        insight = (
            f"Algorithm shift ({direction}): Increase {', '.join(increase_types)}. "
            f"Reduce {', '.join(decrease_types)}. "
            f"Shift {adaptation.get('shift_percentage', 20)}% of content mix."
        )

        evidence = {
            "source": "algorithm_shift_detection",
            "shift_data": shift_data,
            "adaptation": adaptation,
        }

        # Deactivate conflicting old entries for this client/platform
        old_entries = (
            db.query(PlatformIntelligence)
            .filter(
                PlatformIntelligence.client_id == client.id,
                PlatformIntelligence.platform == platform,
                PlatformIntelligence.category == "required_to_play",
                PlatformIntelligence.is_active == 1,
            )
            .all()
        )

        for old_entry in old_entries:
            # Deactivate entries related to algorithm shifts
            if "algorithm" in old_entry.insight.lower() or "shift" in old_entry.insight.lower():
                old_entry.is_active = 0

        record = PlatformIntelligence(
            client_id=client.id,
            platform=platform,
            category="required_to_play",
            insight=insight,
            evidence=evidence,
            effective_date=datetime.now(timezone.utc),
            is_active=1,
        )
        db.add(record)
        new_records.append(record)

    db.commit()

    # Refresh all new records
    for record in new_records:
        db.refresh(record)

    logger.info(
        "Merged algorithm shift into playbook for %d clients on %s",
        len(new_records),
        platform,
    )

    return new_records
