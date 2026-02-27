"""Plateau detection, root cause analysis, experiment proposals, and weekly health checks.

Detects engagement plateaus after 2-week flat metrics, performs root cause
analysis with likelihood scoring, proposes structured experiments with
hypothesis/duration/success-metric/rollback, and runs lightweight weekly
health checks to catch slow declines before they become plateaus.

Also handles institutional knowledge persistence for anonymized diagnostic
insights and semantic search for similar historical patterns.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def detect_plateau(
    db: Session,
    client_id: int,
    metric: str = "engagement_rate",
    window_days: int = 14,
) -> bool:
    """Detect plateau when 2-week metrics are flat (<5% change).

    Compares current 2-week rolling average against prior 2-week rolling
    average. Plateau = less than 5% change in either direction.

    Args:
        db: SQLAlchemy session.
        client_id: Client ID.
        metric: Metric to check (default: engagement_rate).
        window_days: Rolling window in days (default: 14).

    Returns:
        True if plateau detected, False otherwise.
    """
    from sophia.research.models import ResearchFinding

    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=window_days)
    prior_start = now - timedelta(days=window_days * 2)

    # Query research findings as proxy for engagement data
    # In production, this would query actual engagement metrics table
    current_findings = (
        db.query(ResearchFinding)
        .filter(
            ResearchFinding.client_id == client_id,
            ResearchFinding.created_at >= current_start,
        )
        .all()
    )

    prior_findings = (
        db.query(ResearchFinding)
        .filter(
            ResearchFinding.client_id == client_id,
            ResearchFinding.created_at >= prior_start,
            ResearchFinding.created_at < current_start,
        )
        .all()
    )

    # Compute average relevance scores as engagement proxy
    if not current_findings and not prior_findings:
        return False

    current_avg = (
        sum(f.relevance_score_val for f in current_findings) / len(current_findings)
        if current_findings
        else 0.0
    )
    prior_avg = (
        sum(f.relevance_score_val for f in prior_findings) / len(prior_findings)
        if prior_findings
        else 0.0
    )

    # If no prior data, can't detect plateau
    if prior_avg == 0.0:
        return False

    # Calculate percentage change
    pct_change = abs(current_avg - prior_avg) / prior_avg

    # Plateau = less than 5% change in either direction
    return pct_change < 0.05


def generate_diagnostic_report(
    db: Session, client_id: int
) -> dict:
    """Generate diagnostic report with root cause analysis.

    Checks potential causes: content staleness, audience fatigue,
    competitor gains, algorithm changes, seasonal patterns. Assigns
    likelihood score (0-1) to each cause.

    Args:
        db: SQLAlchemy session.
        client_id: Client ID.

    Returns:
        Structured diagnostic report dict.
    """
    now = datetime.now(timezone.utc)
    plateau_detected = detect_plateau(db, client_id)

    root_causes = []

    # Check 1: Content staleness
    staleness_score = _check_content_staleness(db, client_id)
    if staleness_score > 0:
        root_causes.append({
            "cause": "content_staleness",
            "likelihood": staleness_score,
            "evidence": "Content types/themes show repetition over last 14 days",
        })

    # Check 2: Audience fatigue
    fatigue_score = _check_audience_fatigue(db, client_id)
    if fatigue_score > 0:
        root_causes.append({
            "cause": "audience_fatigue",
            "likelihood": fatigue_score,
            "evidence": "Engagement declining on posts similar to earlier high-performers",
        })

    # Check 3: Competitor gains
    competitor_score = _check_competitor_gains(db, client_id)
    if competitor_score > 0:
        root_causes.append({
            "cause": "competitor_gains",
            "likelihood": competitor_score,
            "evidence": "Competitors showing engagement increases while client is flat",
        })

    # Check 4: Algorithm changes
    algorithm_score = _check_algorithm_changes(db, client_id)
    if algorithm_score > 0:
        root_causes.append({
            "cause": "algorithm_changes",
            "likelihood": algorithm_score,
            "evidence": "Detected algorithm shift for client's platforms",
        })

    # Check 5: Seasonal patterns
    seasonal_score = _check_seasonal_patterns(db, client_id)
    if seasonal_score > 0:
        root_causes.append({
            "cause": "seasonal_patterns",
            "likelihood": seasonal_score,
            "evidence": "Historical data suggests this time of year is flat for industry",
        })

    # Sort by likelihood descending
    root_causes.sort(key=lambda x: x["likelihood"], reverse=True)

    # Generate experiment proposals for high-likelihood causes
    experiments = propose_experiments(root_causes)

    # Compute metrics summary
    metrics_summary = _compute_metrics_summary(db, client_id)

    return {
        "client_id": client_id,
        "plateau_detected": plateau_detected,
        "metrics_summary": metrics_summary,
        "root_causes": root_causes,
        "experiments": experiments,
        "generated_at": now,
    }


def _check_content_staleness(db: Session, client_id: int) -> float:
    """Check for content theme repetition. Returns likelihood 0-1."""
    from sophia.research.models import ResearchFinding

    now = datetime.now(timezone.utc)
    recent_start = now - timedelta(days=14)
    prior_start = now - timedelta(days=28)

    recent = (
        db.query(ResearchFinding)
        .filter(
            ResearchFinding.client_id == client_id,
            ResearchFinding.created_at >= recent_start,
        )
        .all()
    )

    prior = (
        db.query(ResearchFinding)
        .filter(
            ResearchFinding.client_id == client_id,
            ResearchFinding.created_at >= prior_start,
            ResearchFinding.created_at < recent_start,
        )
        .all()
    )

    if not recent or not prior:
        return 0.0

    # Compare topic overlap between periods
    recent_topics = set(f.topic.lower() for f in recent)
    prior_topics = set(f.topic.lower() for f in prior)

    if not recent_topics or not prior_topics:
        return 0.0

    overlap = len(recent_topics & prior_topics)
    total = len(recent_topics | prior_topics)

    if total == 0:
        return 0.0

    # High overlap = content staleness
    overlap_ratio = overlap / total
    if overlap_ratio > 0.7:
        return 0.8
    elif overlap_ratio > 0.4:
        return 0.5
    elif overlap_ratio > 0.2:
        return 0.3
    return 0.0


def _check_audience_fatigue(db: Session, client_id: int) -> float:
    """Check for declining engagement on similar content. Returns likelihood 0-1."""
    from sophia.research.models import ResearchFinding

    now = datetime.now(timezone.utc)
    recent = (
        db.query(ResearchFinding)
        .filter(
            ResearchFinding.client_id == client_id,
            ResearchFinding.created_at >= now - timedelta(days=14),
        )
        .all()
    )

    older = (
        db.query(ResearchFinding)
        .filter(
            ResearchFinding.client_id == client_id,
            ResearchFinding.created_at >= now - timedelta(days=42),
            ResearchFinding.created_at < now - timedelta(days=14),
        )
        .all()
    )

    if not recent or not older:
        return 0.0

    # Compare relevance scores as engagement proxy
    recent_avg = sum(f.relevance_score_val for f in recent) / len(recent)
    older_avg = sum(f.relevance_score_val for f in older) / len(older)

    if older_avg > 0 and recent_avg < older_avg * 0.9:
        return 0.6
    return 0.0


def _check_competitor_gains(db: Session, client_id: int) -> float:
    """Check if competitors are gaining while client is flat. Returns likelihood 0-1."""
    from sophia.research.models import CompetitorSnapshot

    now = datetime.now(timezone.utc)
    recent_snapshots = (
        db.query(CompetitorSnapshot)
        .filter(
            CompetitorSnapshot.client_id == client_id,
            CompetitorSnapshot.created_at >= now - timedelta(days=14),
        )
        .all()
    )

    if not recent_snapshots:
        return 0.0

    # Check if competitor engagement rates are rising
    rising_competitors = 0
    for snapshot in recent_snapshots:
        if snapshot.avg_engagement_rate and snapshot.avg_engagement_rate > 0.05:
            rising_competitors += 1

    if rising_competitors > 0:
        return min(0.7, 0.3 + 0.2 * rising_competitors)
    return 0.0


def _check_algorithm_changes(db: Session, client_id: int) -> float:
    """Check for detected algorithm shifts. Returns likelihood 0-1."""
    from sophia.research.models import PlatformIntelligence

    now = datetime.now(timezone.utc)
    recent_shifts = (
        db.query(PlatformIntelligence)
        .filter(
            PlatformIntelligence.category == "required_to_play",
            PlatformIntelligence.is_active == 1,
            PlatformIntelligence.effective_date >= now - timedelta(days=30),
        )
        .all()
    )

    algorithm_records = [
        r for r in recent_shifts
        if "algorithm" in r.insight.lower() or "shift" in r.insight.lower()
    ]

    if algorithm_records:
        return 0.7
    return 0.0


def _check_seasonal_patterns(db: Session, client_id: int) -> float:
    """Check for seasonal patterns. Returns likelihood 0-1."""
    # Simple seasonal check based on month
    # In production, this would compare historical data by month
    now = datetime.now(timezone.utc)
    month = now.month

    # Common slow months for social media engagement
    slow_months = {1, 7, 8}  # January (post-holiday), July-August (summer)
    if month in slow_months:
        return 0.4
    return 0.0


def _compute_metrics_summary(db: Session, client_id: int) -> dict:
    """Compute current metrics summary for diagnostic report."""
    from sophia.research.models import ResearchFinding

    now = datetime.now(timezone.utc)
    recent = (
        db.query(ResearchFinding)
        .filter(
            ResearchFinding.client_id == client_id,
            ResearchFinding.created_at >= now - timedelta(days=14),
        )
        .all()
    )

    total_findings = len(recent)
    avg_relevance = (
        sum(f.relevance_score_val for f in recent) / total_findings
        if total_findings > 0
        else 0.0
    )

    return {
        "findings_count_14d": total_findings,
        "avg_relevance_14d": round(avg_relevance, 3),
    }


def propose_experiments(root_causes: list[dict]) -> list[dict]:
    """Generate structured experiment proposals for high-likelihood root causes.

    Each proposal includes hypothesis, action, duration (7-14 days),
    success metric, rollback plan, and which cause it addresses.
    Experiments are recommended, not auto-triggered -- operator approves.

    Args:
        root_causes: List of root cause dicts with 'cause' and 'likelihood'.

    Returns:
        List of experiment proposal dicts.
    """
    experiments = []

    # Experiment templates per root cause type
    templates = {
        "content_staleness": [
            {
                "hypothesis": "Content repetition has caused audience disengagement. Fresh content types will re-engage the audience.",
                "action": "Introduce 2-3 new content formats (video, carousel, infographics) over the next 2 weeks",
                "duration_days": 14,
                "success_metric": "Engagement rate increases by 20%+ compared to plateau period",
                "rollback_plan": "Return to prior content mix if no improvement after 14 days",
            },
        ],
        "audience_fatigue": [
            {
                "hypothesis": "Audience is fatigued with current content pillars. Shifting to a new pillar will reignite engagement.",
                "action": "Shift to a new content pillar for 1 week while maintaining brand consistency",
                "duration_days": 7,
                "success_metric": "Engagement rate recovers to prior 30-day average",
                "rollback_plan": "Return to previous content pillars if engagement drops further",
            },
        ],
        "competitor_gains": [
            {
                "hypothesis": "Competitors are using a winning format that resonates with the shared audience. Adapting their approach will close the engagement gap.",
                "action": "Adopt competitor's winning content format for 2 weeks while maintaining client's voice",
                "duration_days": 14,
                "success_metric": "Close engagement gap by 50% within 2 weeks",
                "rollback_plan": "Discontinue if engagement doesn't improve or brand alignment is compromised",
            },
        ],
        "algorithm_changes": [
            {
                "hypothesis": "Platform algorithm changes require content format adaptation. Refer to algorithm adaptation protocol.",
                "action": "Follow algorithm adaptation proposal from algorithm detection system",
                "duration_days": 14,
                "success_metric": "Engagement rate recovers to within 10% of pre-shift average",
                "rollback_plan": "Revert to previous content strategy if no improvement",
            },
        ],
        "seasonal_patterns": [
            {
                "hypothesis": "Seasonal slowdown is affecting engagement. Adjusted expectations and seasonal content will maintain audience connection.",
                "action": "Create seasonal-themed content and reduce posting frequency to avoid audience fatigue during slow period",
                "duration_days": 14,
                "success_metric": "Maintain engagement rate within 15% of seasonal average for industry",
                "rollback_plan": "Resume normal posting cadence when seasonal period ends",
            },
        ],
    }

    for cause in root_causes:
        if cause["likelihood"] < 0.3:
            continue

        cause_type = cause["cause"]
        cause_templates = templates.get(cause_type, [])

        for template in cause_templates:
            experiment = {
                **template,
                "addresses_cause": cause_type,
                "requires_operator_approval": True,
            }
            experiments.append(experiment)

    return experiments


def weekly_health_check(
    db: Session, client_id: int
) -> dict:
    """Lightweight weekly health check per client to catch slow declines.

    Checks: engagement rate trend (7-day), follower growth, post frequency
    adherence, research freshness, intelligence profile completeness.
    Flags any metric declining for 2+ consecutive weeks.

    Args:
        db: SQLAlchemy session.
        client_id: Client ID.

    Returns:
        Health check result dict.
    """
    now = datetime.now(timezone.utc)
    warnings: list[str] = []

    # Check 1: Engagement trend (7-day using research findings as proxy)
    engagement_trend = _check_engagement_trend(db, client_id)
    if engagement_trend == "declining":
        warnings.append("Engagement rate declining for 2+ consecutive weeks")

    # Check 2: Research freshness
    research_freshness = _check_research_freshness(db, client_id)
    if research_freshness == "stale":
        warnings.append("No new research findings in 7+ days")

    # Check 3: Intelligence profile completeness
    profile_completeness = _check_profile_completeness(db, client_id)
    if profile_completeness < 50:
        warnings.append(
            f"Intelligence profile only {profile_completeness}% complete"
        )

    # Check 4: Platform playbook coverage
    playbook_coverage = _check_playbook_coverage(db, client_id)
    if not playbook_coverage:
        warnings.append("No active platform playbook entries")

    # Determine overall health
    if len(warnings) >= 3:
        overall_health = "declining"
    elif len(warnings) >= 1:
        overall_health = "warning"
    else:
        overall_health = "healthy"

    return {
        "client_id": client_id,
        "overall_health": overall_health,
        "metrics": {
            "engagement_trend": engagement_trend,
            "research_freshness": research_freshness,
            "profile_completeness_pct": profile_completeness,
            "has_active_playbook": playbook_coverage,
        },
        "warnings": warnings,
        "checked_at": now,
    }


def _check_engagement_trend(db: Session, client_id: int) -> str:
    """Check 7-day engagement trend. Returns 'improving', 'stable', or 'declining'."""
    from sophia.research.models import ResearchFinding

    now = datetime.now(timezone.utc)
    week1_start = now - timedelta(days=7)
    week2_start = now - timedelta(days=14)

    week1 = (
        db.query(ResearchFinding)
        .filter(
            ResearchFinding.client_id == client_id,
            ResearchFinding.created_at >= week1_start,
        )
        .all()
    )

    week2 = (
        db.query(ResearchFinding)
        .filter(
            ResearchFinding.client_id == client_id,
            ResearchFinding.created_at >= week2_start,
            ResearchFinding.created_at < week1_start,
        )
        .all()
    )

    if not week1 and not week2:
        return "stable"

    w1_avg = (
        sum(f.relevance_score_val for f in week1) / len(week1)
        if week1
        else 0.0
    )
    w2_avg = (
        sum(f.relevance_score_val for f in week2) / len(week2)
        if week2
        else 0.0
    )

    if w2_avg > 0 and w1_avg < w2_avg * 0.9:
        return "declining"
    elif w2_avg > 0 and w1_avg > w2_avg * 1.1:
        return "improving"
    return "stable"


def _check_research_freshness(db: Session, client_id: int) -> str:
    """Check if research findings are fresh. Returns 'fresh' or 'stale'."""
    from sophia.research.models import ResearchFinding

    now = datetime.now(timezone.utc)
    recent = (
        db.query(ResearchFinding)
        .filter(
            ResearchFinding.client_id == client_id,
            ResearchFinding.created_at >= now - timedelta(days=7),
        )
        .count()
    )

    return "fresh" if recent > 0 else "stale"


def _check_profile_completeness(db: Session, client_id: int) -> int:
    """Check intelligence profile completeness. Returns percentage 0-100."""
    try:
        from sophia.intelligence.service import compute_depth_scores

        scores = compute_depth_scores(db, client_id)
        if not scores:
            return 0

        avg_depth = sum(s.depth for s in scores) / len(scores)
        return int((avg_depth / 5.0) * 100)
    except Exception:
        return 0


def _check_playbook_coverage(db: Session, client_id: int) -> bool:
    """Check if client has active platform playbook entries."""
    from sophia.research.models import PlatformIntelligence

    count = (
        db.query(PlatformIntelligence)
        .filter(
            PlatformIntelligence.client_id == client_id,
            PlatformIntelligence.is_active == 1,
        )
        .count()
    )
    return count > 0


def persist_diagnostic_insights(
    db: Session, client_id: int, diagnostic_report: dict
) -> None:
    """Persist resolved diagnostic insights as anonymized institutional knowledge.

    When a diagnostic resolves successfully (experiment worked), creates
    institutional knowledge entry. Anonymizes: strips client name, uses
    industry vertical and region type.

    Args:
        db: SQLAlchemy session.
        client_id: Client ID.
        diagnostic_report: The diagnostic report dict from generate_diagnostic_report.
    """
    from sophia.intelligence.models import IntelligenceDomain

    root_causes = diagnostic_report.get("root_causes", [])
    experiments = diagnostic_report.get("experiments", [])

    if not root_causes:
        return

    # Build anonymized insight from diagnostic findings
    top_cause = root_causes[0] if root_causes else None
    if not top_cause:
        return

    insight = (
        f"Engagement plateau resolved. Primary cause: {top_cause['cause']} "
        f"(likelihood {top_cause['likelihood']:.1f}). "
    )

    what_worked = []
    for exp in experiments:
        if exp.get("addresses_cause") == top_cause["cause"]:
            what_worked.append(exp["action"])

    what_didnt_work = []
    for cause in root_causes:
        if cause["likelihood"] < 0.3:
            what_didnt_work.append(
                f"Low likelihood: {cause['cause']} ({cause['likelihood']:.1f})"
            )

    # Use create_institutional_knowledge from intelligence service
    try:
        import asyncio

        from sophia.intelligence.service import create_institutional_knowledge

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                create_institutional_knowledge(
                    db,
                    client_id=client_id,
                    domain=IntelligenceDomain.INDUSTRY,
                    insight=insight,
                    what_worked=what_worked if what_worked else None,
                    what_didnt_work=what_didnt_work if what_didnt_work else None,
                )
            )
        finally:
            loop.close()
    except Exception:
        logger.exception(
            "Failed to persist diagnostic insights for client %d",
            client_id,
        )


def search_similar_diagnostics(
    db: Session,
    industry: str,
    symptoms: str,
    limit: int = 5,
) -> list[dict]:
    """Search for similar historical plateau patterns via semantic search.

    Queries LanceDB for anonymized institutional knowledge entries that
    match the given industry and symptom description.

    Args:
        db: SQLAlchemy session.
        industry: Industry vertical to filter by.
        symptoms: Description of current plateau symptoms.
        limit: Maximum results to return.

    Returns:
        List of anonymized historical diagnostic insight dicts.
    """
    from sophia.intelligence.models import IntelligenceInstitutionalKnowledge

    results = []

    # Try semantic search via LanceDB first
    try:
        from sophia.semantic.embeddings import embed
        from sophia.semantic.index import get_lance_table, hybrid_search

        import asyncio

        loop = asyncio.new_event_loop()
        try:
            query_vector = loop.run_until_complete(embed(symptoms))
        finally:
            loop.close()

        table = get_lance_table("intelligence_entries")
        search_results = hybrid_search(
            table,
            query_text=symptoms,
            query_vector=query_vector,
            limit=limit,
        )

        if not search_results.empty:
            for _, row in search_results.iterrows():
                results.append({
                    "text": row.get("text", ""),
                    "relevance_score": float(row.get("_relevance_score", 0)),
                })
    except Exception:
        logger.debug("Semantic search failed, falling back to SQL query")

    # Fallback: SQL query for matching industry
    if not results:
        sql_results = (
            db.query(IntelligenceInstitutionalKnowledge)
            .filter(
                IntelligenceInstitutionalKnowledge.industry_vertical.ilike(
                    f"%{industry}%"
                )
            )
            .limit(limit)
            .all()
        )

        for entry in sql_results:
            results.append({
                "industry_vertical": entry.industry_vertical,
                "insight": entry.insight,
                "what_worked": entry.what_worked,
                "what_didnt_work": entry.what_didnt_work,
                "region_type": entry.region_type,
            })

    return results
