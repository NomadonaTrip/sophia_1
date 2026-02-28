"""Agent REST API router: briefings, learnings, insights, improvement, patterns.

Provides endpoints for all learning/briefing features. DB dependency
uses the lazy SessionLocal pattern for testability.
"""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from sophia.agent.models import Briefing
from sophia.agent.schemas import (
    BriefingResponse,
    InsightCreate,
    InsightResponse,
    LearningCreate,
    LearningListResponse,
    LearningResponse,
)

agent_router = APIRouter(prefix="/api/agent", tags=["agent"])


# -- DB dependency placeholder ------------------------------------------------


def _get_db():
    """Yield a SQLAlchemy session. Lazy-imports engine to avoid slow NTFS imports at startup."""
    from sophia.db.engine import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -- Briefing Endpoints -------------------------------------------------------


@agent_router.get("/briefings/daily")
def get_latest_daily_briefing(
    db: Session = Depends(_get_db),
) -> BriefingResponse:
    """Return the latest daily standup briefing."""
    briefing = (
        db.query(Briefing)
        .filter_by(briefing_type="daily")
        .order_by(Briefing.generated_at.desc())
        .first()
    )
    if not briefing:
        raise HTTPException(404, "No daily briefing available yet")

    return BriefingResponse(
        id=briefing.id,
        briefing_type=briefing.briefing_type,
        content=json.loads(briefing.content_json),
        generated_at=briefing.generated_at,
    )


@agent_router.get("/briefings/weekly")
def get_latest_weekly_briefing(
    db: Session = Depends(_get_db),
) -> BriefingResponse:
    """Return the latest weekly strategic briefing."""
    briefing = (
        db.query(Briefing)
        .filter_by(briefing_type="weekly")
        .order_by(Briefing.generated_at.desc())
        .first()
    )
    if not briefing:
        raise HTTPException(404, "No weekly briefing available yet")

    return BriefingResponse(
        id=briefing.id,
        briefing_type=briefing.briefing_type,
        content=json.loads(briefing.content_json),
        generated_at=briefing.generated_at,
    )


@agent_router.post("/briefings/daily/generate")
async def trigger_daily_briefing(
    db: Session = Depends(_get_db),
) -> BriefingResponse:
    """Manually trigger daily briefing generation (on-demand)."""
    from sophia.agent.briefing import generate_daily_standup

    content = await generate_daily_standup(db)

    # Return the latest briefing we just created
    briefing = (
        db.query(Briefing)
        .filter_by(briefing_type="daily")
        .order_by(Briefing.generated_at.desc())
        .first()
    )

    return BriefingResponse(
        id=briefing.id,
        briefing_type=briefing.briefing_type,
        content=json.loads(briefing.content_json),
        generated_at=briefing.generated_at,
    )


@agent_router.post("/briefings/weekly/generate")
async def trigger_weekly_briefing(
    db: Session = Depends(_get_db),
) -> BriefingResponse:
    """Manually trigger weekly briefing generation (on-demand)."""
    from sophia.agent.briefing import generate_weekly_briefing

    content = await generate_weekly_briefing(db)

    briefing = (
        db.query(Briefing)
        .filter_by(briefing_type="weekly")
        .order_by(Briefing.generated_at.desc())
        .first()
    )

    return BriefingResponse(
        id=briefing.id,
        briefing_type=briefing.briefing_type,
        content=json.loads(briefing.content_json),
        generated_at=briefing.generated_at,
    )


# -- Learning Endpoints --------------------------------------------------------


@agent_router.get("/learnings")
def list_learnings(
    client_id: Optional[int] = Query(None),
    type: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: Session = Depends(_get_db),
) -> LearningListResponse:
    """List active learnings with optional filters."""
    from sophia.agent.learning import get_active_learnings

    if client_id is None:
        raise HTTPException(400, "client_id is required")

    learnings = get_active_learnings(
        db, client_id=client_id, learning_type=type, limit=limit
    )

    items = [
        LearningResponse.model_validate(l)
        for l in learnings
    ]

    return LearningListResponse(items=items, total=len(items))


@agent_router.post("/learnings", status_code=201)
def create_learning(
    body: LearningCreate,
    db: Session = Depends(_get_db),
) -> LearningResponse:
    """Create a new learning."""
    from sophia.agent.learning import persist_learning

    learning = persist_learning(
        db,
        client_id=body.client_id,
        learning_type=body.learning_type,
        source=body.source,
        content=body.content,
        confidence=body.confidence,
        supersedes_id=body.supersedes_id,
    )

    return LearningResponse.model_validate(learning)


# -- Insight Endpoints ---------------------------------------------------------


@agent_router.post("/insights", status_code=201)
def create_insight(
    body: InsightCreate,
    db: Session = Depends(_get_db),
) -> InsightResponse:
    """Extract and persist a business insight."""
    from sophia.agent.learning import extract_business_insight

    insight = extract_business_insight(
        db,
        client_id=body.client_id,
        category=body.category,
        fact_statement=body.fact_statement,
        source_attribution=body.source_attribution,
        confidence=body.confidence,
    )

    return InsightResponse.model_validate(insight)


@agent_router.get("/insights")
def list_insights(
    client_id: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    db: Session = Depends(_get_db),
) -> list[InsightResponse]:
    """List intelligence entries with optional filters."""
    from sophia.agent.learning import get_client_intelligence

    if client_id is None:
        raise HTTPException(400, "client_id is required")

    insights = get_client_intelligence(db, client_id, category=category)
    return [InsightResponse.model_validate(i) for i in insights]


# -- Improvement Metrics Endpoint ----------------------------------------------


@agent_router.get("/improvement")
def get_improvement_metrics(
    db: Session = Depends(_get_db),
) -> dict:
    """Return ImprovementReport for the last 4 weeks."""
    from sophia.agent.service import calculate_improvement_rate

    report = calculate_improvement_rate(db, weeks_back=4)
    return report.model_dump()


# -- Intelligence Report Endpoint ----------------------------------------------


@agent_router.get("/intelligence-report")
def get_intelligence_report(
    client_id: Optional[int] = Query(None),
    period_days: int = Query(30, ge=7, le=365),
    db: Session = Depends(_get_db),
) -> dict:
    """Generate intelligence report with market signals."""
    from sophia.agent.service import generate_intelligence_report

    report = generate_intelligence_report(
        db, client_id=client_id, period_days=period_days
    )
    return report.model_dump()


# -- Cross-Client Pattern Endpoints --------------------------------------------


@agent_router.get("/patterns/cross-client")
async def get_cross_client_patterns(
    db: Session = Depends(_get_db),
) -> list[dict]:
    """Return detected cross-client patterns (anonymized)."""
    from sophia.agent.briefing import detect_cross_client_patterns

    patterns = await detect_cross_client_patterns(db)
    return [p.model_dump() for p in patterns]


@agent_router.post("/patterns/{pattern_id}/approve")
def approve_pattern(
    pattern_id: int,
    db: Session = Depends(_get_db),
) -> dict:
    """Approve a cross-client pattern for transfer.

    The pattern_id is the source_learning_id from the CrossClientPattern.
    Approving means the operator confirms the pattern should be applied
    to other clients (subject matter only, not voice).
    """
    from sophia.agent.models import Learning

    learning = db.get(Learning, pattern_id)
    if not learning:
        raise HTTPException(404, "Pattern source learning not found")

    # Mark the learning as high-confidence (operator-approved pattern)
    learning.confidence = min(learning.confidence + 0.1, 1.0)
    db.commit()

    return {
        "pattern_id": pattern_id,
        "status": "approved",
        "new_confidence": learning.confidence,
    }


@agent_router.post("/patterns/{pattern_id}/dismiss")
def dismiss_pattern(
    pattern_id: int,
    db: Session = Depends(_get_db),
) -> dict:
    """Dismiss a cross-client pattern.

    Reduces confidence so the pattern is less likely to surface again.
    """
    from sophia.agent.models import Learning

    learning = db.get(Learning, pattern_id)
    if not learning:
        raise HTTPException(404, "Pattern source learning not found")

    learning.confidence = max(learning.confidence - 0.2, 0.1)
    db.commit()

    return {
        "pattern_id": pattern_id,
        "status": "dismissed",
        "new_confidence": learning.confidence,
    }
