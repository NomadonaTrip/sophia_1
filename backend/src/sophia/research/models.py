"""Research data models: findings, competitors, snapshots, platform intelligence.

All models inherit from Base and TimestampMixin. Research findings have
time-based decay windows that determine relevance score. Competitor models
support primary vs watchlist monitoring. Platform intelligence categorizes
insights as 'required_to_play' or 'sufficient_to_win'.
"""

from datetime import datetime, timedelta, timezone
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from sophia.db.base import Base, TimestampMixin


class FindingType(str, PyEnum):
    """Type of research finding, determines decay window."""

    NEWS = "news"  # Decays in 2-3 days
    TREND = "trend"  # Decays in 1-2 weeks
    INDUSTRY = "industry"  # Decays in 4-8 weeks
    COMMUNITY = "community"  # Decays in 1 week


# Configurable decay windows per finding type
DECAY_WINDOWS: dict[FindingType, timedelta] = {
    FindingType.NEWS: timedelta(days=3),
    FindingType.TREND: timedelta(days=14),
    FindingType.INDUSTRY: timedelta(days=56),
    FindingType.COMMUNITY: timedelta(days=7),
}


def relevance_score(finding_type: FindingType, created_at: datetime) -> float:
    """Calculate time-decayed relevance score (0.0 to 1.0).

    Returns 0.0 when the finding has passed its decay window.
    Uses linear decay from 1.0 at creation to 0.0 at window end.

    Args:
        finding_type: The type of finding (determines decay window).
        created_at: When the finding was created.

    Returns:
        Float between 0.0 and 1.0 representing current relevance.
    """
    window = DECAY_WINDOWS[finding_type]
    now = datetime.now(timezone.utc)
    # Ensure created_at is timezone-aware
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age = now - created_at
    if age >= window:
        return 0.0
    return 1.0 - (age / window)


class ResearchFinding(TimestampMixin, Base):
    """Research finding with time-based decay and content angles.

    Each finding includes 1-2 suggested content angles per client.
    Confidence is based on source count and reliability.
    Time-sensitive findings trigger push notifications.
    """

    __tablename__ = "research_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False, index=True
    )
    finding_type: Mapped[FindingType] = mapped_column(
        Enum(FindingType), nullable=False
    )
    topic: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    from sqlalchemy import JSON

    content_angles: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True
    )  # JSON list of 1-2 suggested angles

    source_url: Mapped[Optional[str]] = mapped_column(
        String(2000), nullable=True
    )
    source_name: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )
    relevance_score_val: Mapped[float] = mapped_column(
        "relevance_score", Float, default=1.0, nullable=False
    )
    confidence: Mapped[float] = mapped_column(
        Float, default=0.5, nullable=False
    )
    is_time_sensitive: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )  # Boolean: triggers push notification
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )  # Computed from finding_type decay window

    __table_args__ = (
        Index("ix_research_findings_client_type", "client_id", "finding_type"),
    )


class Competitor(TimestampMixin, Base):
    """Competitor tracked per client.

    3-5 primary competitors with daily monitoring.
    Additional competitors on watchlist with monthly deep-scan.
    Can be operator-seeded or sophia-discovered (requires approval).
    """

    __tablename__ = "competitors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    from sqlalchemy import JSON

    platform_urls: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )  # {"facebook": "url", "instagram": "url"}

    is_primary: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False
    )  # Boolean: primary (3-5) vs watchlist
    is_operator_approved: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )  # Boolean: operator confirmed
    discovered_by: Mapped[str] = mapped_column(
        String(50), default="operator", nullable=False
    )  # "operator" or "sophia"
    last_monitored_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    monitoring_frequency: Mapped[str] = mapped_column(
        String(20), default="daily", nullable=False
    )  # daily (primary) or monthly (watchlist)


class CompetitorSnapshot(TimestampMixin, Base):
    """Point-in-time snapshot of a competitor's social media activity.

    Captures posting frequency, engagement, content themes, and
    detected opportunities (gaps and threats).
    """

    __tablename__ = "competitor_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False, index=True
    )
    competitor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("competitors.id"), nullable=False, index=True
    )
    post_frequency_7d: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    avg_engagement_rate: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )

    from sqlalchemy import JSON

    top_content_themes: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True
    )  # JSON list of themes
    content_tone: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # professional, casual, humorous, educational

    detected_gaps: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True
    )  # JSON: content gaps we could fill
    detected_threats: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True
    )  # JSON: competitive threats
    opportunity_type: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )  # "reactive" or "proactive"


class PlatformIntelligence(TimestampMixin, Base):
    """Per-client, per-platform intelligence entry.

    Categorized as 'required_to_play' (table-stakes) or
    'sufficient_to_win' (differentiating practices).
    """

    __tablename__ = "platform_intelligence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False, index=True
    )
    platform: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # facebook, instagram
    category: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # required_to_play, sufficient_to_win
    insight: Mapped[str] = mapped_column(Text, nullable=False)

    from sqlalchemy import JSON

    evidence: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )  # JSON: supporting performance data

    effective_date: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    is_active: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False
    )  # Boolean: still current
