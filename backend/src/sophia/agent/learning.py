"""Learning persistence service: store, retrieve, and supersede structured learnings.

Every learning must be a structured fact, pattern, or insight -- NOT raw
conversation transcript or chat replay. The persist_learning function
enforces this by design: callers are responsible for distilling conversation
into concrete learnings before calling this service.

Write-through to LanceDB: after SQLite commit, each learning is embedded
for semantic search. If LanceDB sync fails, the error is logged but NOT
raised (SQLite is the source of truth).
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from sophia.agent.models import BusinessInsight, Learning

logger = logging.getLogger(__name__)


def persist_learning(
    db: Session,
    client_id: int,
    learning_type: str,
    source: str,
    content: str,
    confidence: float = 0.8,
    supersedes_id: Optional[int] = None,
    cycle_run_id: Optional[int] = None,
) -> Learning:
    """Persist a structured learning to the database.

    IMPORTANT: Every learning must be a distilled fact, pattern, or insight.
    Do NOT pass raw conversation transcripts or chat replays. The caller
    is responsible for extracting structured knowledge before calling this
    function.

    If supersedes_id is provided, the old learning is marked as superseded
    and linked to this new learning via the supersession chain.

    After SQLite commit, triggers write-through to LanceDB for semantic
    search. LanceDB failures are logged but do not fail the operation.

    Args:
        db: SQLAlchemy session.
        client_id: Client this learning belongs to.
        learning_type: One of LearningType enum values.
        source: Origin identifier (e.g., "cycle_approval", "operator_chat").
        content: The structured learning text.
        confidence: Confidence level (0.0-1.0, default 0.8).
        supersedes_id: Optional ID of a learning this one replaces.
        cycle_run_id: Optional cycle run ID if learning came from a cycle.

    Returns:
        The newly created Learning record.
    """
    learning = Learning(
        client_id=client_id,
        learning_type=learning_type,
        source=source,
        content=content,
        confidence=confidence,
        cycle_run_id=cycle_run_id,
    )
    db.add(learning)
    db.flush()  # Get the ID assigned

    if supersedes_id is not None:
        mark_superseded(db, supersedes_id, learning.id)

    db.commit()

    # Write-through to LanceDB for semantic search
    _sync_learning_to_lance(learning)

    return learning


def mark_superseded(db: Session, old_learning_id: int, new_learning_id: int) -> None:
    """Mark an old learning as superseded by a newer one.

    Args:
        db: SQLAlchemy session.
        old_learning_id: ID of the learning being superseded.
        new_learning_id: ID of the learning that replaces it.
    """
    old_learning = db.get(Learning, old_learning_id)
    if old_learning is None:
        logger.warning(
            "Cannot supersede learning %d: not found", old_learning_id
        )
        return

    old_learning.is_superseded = True
    old_learning.superseded_by_id = new_learning_id
    db.flush()


def get_active_learnings(
    db: Session,
    client_id: int,
    learning_type: Optional[str] = None,
    limit: int = 50,
) -> list[Learning]:
    """Retrieve active (non-superseded) learnings for a client.

    Args:
        db: SQLAlchemy session.
        client_id: Client to retrieve learnings for.
        learning_type: Optional filter by learning type.
        limit: Maximum number of results (default 50).

    Returns:
        List of active Learning records, ordered by created_at desc.
    """
    query = (
        db.query(Learning)
        .filter(
            Learning.client_id == client_id,
            Learning.is_superseded == False,  # noqa: E712
        )
    )

    if learning_type is not None:
        query = query.filter(Learning.learning_type == learning_type)

    return (
        query.order_by(Learning.created_at.desc(), Learning.id.desc())
        .limit(limit)
        .all()
    )


def extract_business_insight(
    db: Session,
    client_id: int,
    category: str,
    fact_statement: str,
    source_attribution: str,
    confidence: float = 0.8,
) -> BusinessInsight:
    """Extract and persist a structured business insight (LRNG-04).

    Creates a BusinessInsight record for progressive client intelligence.
    Each entry is a concrete fact about the client's business domain.

    After SQLite commit, triggers write-through to LanceDB for semantic
    search across intelligence entries.

    Args:
        db: SQLAlchemy session.
        client_id: Client this insight belongs to.
        category: One of InsightCategory enum values.
        fact_statement: The extracted fact.
        source_attribution: Where the insight came from.
        confidence: Confidence level (0.0-1.0, default 0.8).

    Returns:
        The newly created BusinessInsight record.
    """
    insight = BusinessInsight(
        client_id=client_id,
        category=category,
        fact_statement=fact_statement,
        source_attribution=source_attribution,
        confidence=confidence,
    )
    db.add(insight)
    db.commit()

    # Write-through to LanceDB for semantic search
    _sync_insight_to_lance(insight)

    return insight


def get_client_intelligence(
    db: Session,
    client_id: int,
    category: Optional[str] = None,
) -> list[BusinessInsight]:
    """Retrieve active intelligence entries for a client.

    Args:
        db: SQLAlchemy session.
        client_id: Client to retrieve insights for.
        category: Optional filter by InsightCategory.

    Returns:
        List of active BusinessInsight records.
    """
    query = db.query(BusinessInsight).filter(
        BusinessInsight.client_id == client_id,
        BusinessInsight.is_active == True,  # noqa: E712
    )

    if category is not None:
        query = query.filter(BusinessInsight.category == category)

    return query.order_by(BusinessInsight.created_at.desc()).all()


# ---------------------------------------------------------------------------
# LanceDB write-through (best-effort)
# ---------------------------------------------------------------------------


def _sync_learning_to_lance(learning: Learning) -> None:
    """Write-through a learning to LanceDB. Failures are logged, not raised."""
    try:
        from sophia.semantic.sync import sync_to_lance
        import asyncio

        asyncio.get_event_loop().run_until_complete(
            sync_to_lance(
                record_type="learnings",
                record_id=learning.id,
                text=f"{learning.learning_type}: {learning.content}",
                metadata={
                    "client_id": learning.client_id,
                    "domain": learning.learning_type,
                    "created_at": (
                        learning.created_at.isoformat()
                        if learning.created_at
                        else ""
                    ),
                },
            )
        )
    except Exception:
        logger.exception(
            "LANCE_SYNC_FAILED: Failed to sync learning %d to LanceDB. "
            "SQLite data is safe.",
            learning.id,
        )


def _sync_insight_to_lance(insight: BusinessInsight) -> None:
    """Write-through a business insight to LanceDB. Failures are logged, not raised."""
    try:
        from sophia.semantic.sync import sync_to_lance
        import asyncio

        asyncio.get_event_loop().run_until_complete(
            sync_to_lance(
                record_type="business_insights",
                record_id=insight.id,
                text=f"{insight.category}: {insight.fact_statement}",
                metadata={
                    "client_id": insight.client_id,
                    "domain": insight.category,
                    "created_at": (
                        insight.created_at.isoformat()
                        if insight.created_at
                        else ""
                    ),
                },
            )
        )
    except Exception:
        logger.exception(
            "LANCE_SYNC_FAILED: Failed to sync insight %d to LanceDB. "
            "SQLite data is safe.",
            insight.id,
        )
