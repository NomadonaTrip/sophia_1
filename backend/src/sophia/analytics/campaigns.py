"""Campaign auto-grouping and aggregate metrics.

Groups published/approved content drafts into campaigns by content pillar
and calendar month. Computes campaign-level aggregate engagement metrics.

All functions take a SQLAlchemy session as first arg for testability
via transaction rollback.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from sophia.analytics.models import (
    Campaign,
    CampaignMembership,
    EngagementMetric,
)

logger = logging.getLogger(__name__)

# Month names for campaign naming
_MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _slugify(text: str) -> str:
    """Convert text to URL-safe slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def auto_group_campaigns(
    db: Session, client_id: int
) -> list[Campaign]:
    """Auto-group content drafts into campaigns by content pillar and month.

    Steps:
    1. Query published/approved ContentDrafts not already in a campaign
    2. Group by (content_pillar, calendar month)
    3. Create or find existing Campaign per group
    4. Create CampaignMembership links

    Args:
        db: SQLAlchemy session.
        client_id: Client whose drafts to group.

    Returns:
        List of campaigns created or updated.
    """
    from sophia.content.models import ContentDraft

    # Get draft IDs already in campaigns
    existing_draft_ids = set(
        row[0]
        for row in db.query(CampaignMembership.content_draft_id).all()
    )

    # Query ungrouped published/approved drafts
    drafts = (
        db.query(ContentDraft)
        .filter(
            ContentDraft.client_id == client_id,
            ContentDraft.status.in_(["published", "approved"]),
        )
        .all()
    )

    # Filter out already-grouped drafts
    ungrouped = [d for d in drafts if d.id not in existing_draft_ids]

    if not ungrouped:
        return []

    # Group by (content_pillar, year-month)
    groups: dict[tuple[str, int, int], list] = defaultdict(list)
    for draft in ungrouped:
        pillar = draft.content_pillar or "General"
        # Use created_at for grouping since published_at may be None for approved
        ref_date = draft.published_at or draft.created_at
        year = ref_date.year
        month = ref_date.month
        groups[(pillar, year, month)].append(draft)

    campaigns_touched = []
    for (pillar, year, month), group_drafts in groups.items():
        # Generate campaign name and slug
        month_name = _MONTH_NAMES[month]
        campaign_name = f"{pillar} - {month_name} {year}"
        slug = _slugify(campaign_name)

        # Find or create campaign
        from datetime import date

        month_start = date(year, month, 1)
        # End of month
        if month == 12:
            month_end = date(year + 1, 1, 1)
        else:
            month_end = date(year, month + 1, 1)

        existing = (
            db.query(Campaign)
            .filter(
                Campaign.client_id == client_id,
                Campaign.content_pillar == pillar,
                Campaign.start_date == month_start,
            )
            .first()
        )

        if existing:
            campaign = existing
        else:
            campaign = Campaign(
                client_id=client_id,
                name=campaign_name,
                slug=slug,
                start_date=month_start,
                end_date=month_end,
                content_pillar=pillar,
                status="active",
            )
            db.add(campaign)
            db.flush()

        # Create memberships
        for draft in group_drafts:
            membership = CampaignMembership(
                campaign_id=campaign.id,
                content_draft_id=draft.id,
            )
            db.add(membership)

        campaigns_touched.append(campaign)

    db.flush()

    logger.info(
        "Auto-grouped %d drafts into %d campaigns for client %d",
        len(ungrouped),
        len(campaigns_touched),
        client_id,
    )

    return campaigns_touched


def compute_campaign_metrics(db: Session, campaign_id: int) -> dict:
    """Compute aggregate engagement metrics for a campaign.

    Aggregates EngagementMetric data across all drafts in the campaign
    via CampaignMembership.

    Args:
        db: SQLAlchemy session.
        campaign_id: Campaign to compute metrics for.

    Returns:
        Dict with total_reach, total_engagement, avg_engagement_rate,
        total_clicks, total_saves, total_shares, post_count.
    """
    # Get draft IDs in this campaign
    draft_ids = [
        row[0]
        for row in db.query(CampaignMembership.content_draft_id)
        .filter(CampaignMembership.campaign_id == campaign_id)
        .all()
    ]

    if not draft_ids:
        return {
            "total_reach": 0,
            "total_engagement": 0,
            "avg_engagement_rate": 0.0,
            "total_clicks": 0,
            "total_saves": 0,
            "total_shares": 0,
            "post_count": 0,
        }

    # Query metrics for these drafts
    metrics = (
        db.query(EngagementMetric)
        .filter(EngagementMetric.content_draft_id.in_(draft_ids))
        .all()
    )

    # Aggregate
    totals: dict[str, float] = defaultdict(float)
    for m in metrics:
        totals[m.metric_name] += m.metric_value

    total_reach = totals.get("reach", 0)
    total_likes = totals.get("likes", 0)
    total_comments = totals.get("comments", 0)
    total_shares = totals.get("shares", 0)
    total_saves = totals.get("saved", 0)
    total_clicks = totals.get("link_clicks", 0)

    total_engagement = total_likes + total_comments + total_shares + total_saves
    avg_engagement_rate = 0.0
    if total_reach > 0:
        avg_engagement_rate = round(total_engagement / total_reach * 100, 2)

    return {
        "total_reach": int(total_reach),
        "total_engagement": int(total_engagement),
        "avg_engagement_rate": avg_engagement_rate,
        "total_clicks": int(total_clicks),
        "total_saves": int(total_saves),
        "total_shares": int(total_shares),
        "post_count": len(draft_ids),
    }


def list_campaigns(
    db: Session, client_id: int, status: Optional[str] = None
) -> list[Campaign]:
    """List campaigns for a client, optionally filtered by status.

    Args:
        db: SQLAlchemy session.
        client_id: Client whose campaigns to list.
        status: Optional status filter ("active", "completed", etc.).

    Returns:
        List of Campaign objects ordered by start_date descending.
    """
    query = db.query(Campaign).filter(Campaign.client_id == client_id)
    if status:
        query = query.filter(Campaign.status == status)
    return query.order_by(Campaign.start_date.desc()).all()
