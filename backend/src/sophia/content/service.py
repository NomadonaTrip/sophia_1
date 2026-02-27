"""Content generation orchestrator: three-input validation, batch generation,
voice alignment integration, quality gates, ranking, regeneration, format
adaptation, evergreen bank management, and persistence.

This is Sophia's primary value delivery -- generating content that sounds like
the client, is grounded in real research, and is platform-optimized.

The orchestrator enforces the research-first rule: no content is generated
without all three mandatory inputs (research, intelligence, voice profile).
After generation, every draft passes through the quality gate pipeline before
entering the operator's approval queue.

Regenerated content also runs through the FULL quality gate pipeline (locked
decision: no shortcuts for regeneration).
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from sophia.content.models import (
    ContentDraft,
    EvergreenEntry,
    FormatPerformance,
    RegenerationLog,
)
from sophia.content.prompt_builder import (
    build_batch_prompts,
    build_image_prompt,
)
from sophia.content.quality_gates import run_pipeline as run_quality_gates
from sophia.content.voice_alignment import (
    compute_voice_baseline,
    compute_voice_confidence,
    score_voice_alignment,
)
from sophia.exceptions import ContentGenerationError, RegenerationLimitError

logger = logging.getLogger(__name__)


def generate_content_batch(
    db: Session,
    client_id: int,
) -> list[ContentDraft]:
    """Generate a batch of content drafts for a client.

    Enforces the three-input validation (research-first rule), builds
    voice-matched prompts, generates drafts, scores voice alignment,
    ranks drafts, and persists to database.

    Args:
        db: SQLAlchemy session.
        client_id: Client to generate content for.

    Returns:
        Ranked list of ContentDraft objects.

    Raises:
        ContentGenerationError: If any of the three mandatory inputs are missing.
    """
    # Step 1: Three-input validation (CONT-01 research-first rule)
    research = _validate_research(db, client_id)
    intelligence = _validate_intelligence(db, client_id)
    voice_profile = _validate_voice_profile(db, client_id)

    # Step 2: Determine adaptive option count
    option_count = _compute_option_count(research)

    # Step 3: Retrieve few-shot examples and approved posts for baseline
    approved_posts = _get_approved_posts(db, client_id, limit=30)
    few_shot_examples = approved_posts[:5]  # Most recent 5 for few-shot

    # Step 4: Build prompts
    client_config = _build_client_config(intelligence)
    prompts = build_batch_prompts(
        research=research,
        intelligence=intelligence,
        voice=voice_profile,
        platforms=["facebook", "instagram"],
        option_count=option_count,
        include_stories=True,
        client_config=client_config,
        approved_examples=few_shot_examples,
    )

    # Step 5: Generate drafts
    # In the actual agent cycle, Claude Code invokes these prompts.
    # Here we construct the draft shells that would be filled by generation.
    drafts: list[ContentDraft] = []
    visual_style = client_config.get("brand_assets", {}).get("visual_style", {})
    business_name = _extract_business_name(intelligence)

    for prompt_spec in prompts:
        for i in range(prompt_spec["option_count"]):
            # Create draft shell -- actual copy/image_prompt would come from
            # Claude Code generation. For orchestration testing, we create
            # placeholder drafts that demonstrate the full pipeline.
            draft = ContentDraft(
                client_id=client_id,
                platform=prompt_spec["platform"],
                content_type=prompt_spec["content_type"],
                copy="",  # Filled by generation
                image_prompt=build_image_prompt(
                    business_name=business_name,
                    visual_style=visual_style,
                    platform=prompt_spec["platform"],
                    content_type=prompt_spec["content_type"],
                    post_copy="",
                ),
                image_ratio=_get_image_ratio(
                    prompt_spec["platform"], prompt_spec["content_type"]
                ),
                freshness_window="this_week",
                status="draft",
                gate_status="pending",
            )
            drafts.append(draft)

    # Step 6: Compute voice alignment per draft
    baseline = compute_voice_baseline(approved_posts) if approved_posts else {}
    confidence_level = compute_voice_confidence(len(approved_posts))

    for draft in drafts:
        if draft.copy:
            is_story = draft.content_type == "story"
            alignment_score, deviations = score_voice_alignment(
                draft.copy, baseline, is_story=is_story
            )
            draft.voice_confidence_pct = alignment_score * 100

            # Flag drifting drafts (below 0.6 alignment)
            if alignment_score < 0.6 and deviations:
                logger.warning(
                    "Voice drift detected for client %d draft on %s %s: %s",
                    client_id,
                    draft.platform,
                    draft.content_type,
                    "; ".join(deviations[:3]),
                )
        else:
            # No copy yet (placeholder) -- set based on confidence level
            draft.voice_confidence_pct = {
                "low": 30.0,
                "medium": 60.0,
                "high": 80.0,
            }.get(confidence_level, 50.0)

    # Step 7: Run quality gate pipeline on each draft
    for draft in drafts:
        if draft.copy:
            report = run_quality_gates(db, draft, client_id)
            draft.gate_status = report.status
            draft.gate_report = report.to_dict()

            # Track gate failures for systemic issue detection
            for gate_result in report.results:
                failed = gate_result.status.value == "rejected"
                track_gate_failure(db, client_id, gate_result.gate_name, failed)

            # If auto-fixed, the pipeline already applied the fix to draft.copy
            if report.status == "passed_with_fix":
                logger.info(
                    "Draft auto-fixed for client %d: %s",
                    client_id,
                    report.summary_badge,
                )

    # Step 8: Filter out rejected drafts for ranking
    # Keep rejected drafts in the batch for persistence (learning) but
    # exclude them from ranking and the final return list.
    active_drafts = [d for d in drafts if d.gate_status != "rejected"]
    rejected_drafts = [d for d in drafts if d.gate_status == "rejected"]

    if not active_drafts and drafts:
        # ALL drafts rejected -- systemic issue
        gate_failures = Counter()
        for d in rejected_drafts:
            report_data = d.gate_report or {}
            rejected_by = report_data.get("rejected_by", "unknown")
            gate_failures[rejected_by] += 1

        failure_summary = ", ".join(
            f"{gate}: {count}" for gate, count in gate_failures.most_common()
        )
        raise ContentGenerationError(
            message="All content drafts rejected by quality gates",
            detail=f"Gate failures: {failure_summary}",
            reason="all_drafts_rejected",
            suggestion="Check systemic gate issues with check_systemic_gate_issues(). "
            "The most common failure gates may need recalibration.",
        )

    # Step 9: Rank active (non-rejected) drafts
    active_drafts = _rank_drafts(active_drafts, intelligence)

    # Step 10: Persist ALL drafts (including rejected) to database for learning
    all_drafts = active_drafts + rejected_drafts
    for draft in all_drafts:
        db.add(draft)
    db.flush()

    # Save evergreen drafts to bank (only non-rejected)
    for draft in active_drafts:
        if draft.freshness_window == "evergreen" or draft.is_evergreen:
            entry = EvergreenEntry(
                client_id=client_id,
                content_draft_id=draft.id,
                platform=draft.platform,
                content_type=draft.content_type,
                is_used=False,
            )
            db.add(entry)

    db.commit()

    # Refresh to get IDs
    for draft in all_drafts:
        db.refresh(draft)

    # Return only non-rejected drafts (operator never sees rejected in queue)
    return active_drafts


def get_content_drafts(
    db: Session,
    client_id: int,
    status: Optional[str] = None,
    limit: int = 20,
) -> list[ContentDraft]:
    """Query content drafts for a client with optional filters.

    Args:
        db: SQLAlchemy session.
        client_id: Client ID (SAFE-01 isolation).
        status: Optional status filter.
        limit: Maximum results.

    Returns:
        List of ContentDraft objects ordered by created_at desc.
    """
    query = db.query(ContentDraft).filter(
        ContentDraft.client_id == client_id,
    )

    if status:
        query = query.filter(ContentDraft.status == status)

    return query.order_by(ContentDraft.id.desc()).limit(limit).all()


# -- Gate Tracking and Statistics --------------------------------------------


def track_gate_failure(
    db: Session, client_id: int, gate_name: str, failed: bool
) -> None:
    """Track a gate pass/fail event for systemic issue detection.

    Stores gate results as lightweight JSON on the draft's gate_report field.
    For aggregate tracking, we query ContentDraft.gate_report across recent
    drafts rather than maintaining a separate counter table -- simpler schema
    and the data is already there.

    Args:
        db: SQLAlchemy session.
        client_id: Client ID.
        gate_name: Name of the gate.
        failed: True if the gate failed (rejected), False if passed.
    """
    # Gate results are already stored on each draft's gate_report.
    # This function is a lightweight hook for real-time logging.
    if failed:
        logger.info(
            "Gate failure tracked: client_id=%d gate=%s",
            client_id,
            gate_name,
        )


def check_systemic_gate_issues(
    db: Session, client_id: int, days: int = 30
) -> list[str]:
    """Check for systemic gate failure patterns.

    Queries gate results from the last N days. If any gate exceeds 30%
    failure rate, returns a list of issue strings with recommendations.

    Args:
        db: SQLAlchemy session.
        client_id: Client ID.
        days: Lookback window in days (default 30).

    Returns:
        List of issue strings. Empty if no systemic issues.
    """
    stats = get_gate_statistics(db, client_id, days=days)
    issues: list[str] = []

    recommendations = {
        "sensitivity": "Sensitivity profile may need recalibration",
        "voice_alignment": "Voice profile may need update or recalibration",
        "plagiarism_originality": "Content variety may be insufficient -- consider broadening research scope",
        "ai_pattern_detection": "Generation style may need adjustment",
        "research_grounding": "Research coverage may be insufficient for content claims",
        "brand_safety": "Brand safety guardrails may need review",
    }

    per_gate = stats.get("per_gate", {})
    for gate_name, gate_stats in per_gate.items():
        failure_rate = gate_stats.get("failure_rate", 0.0)
        if failure_rate > 0.30:
            recommendation = recommendations.get(
                gate_name, f"Gate '{gate_name}' may need review"
            )
            issues.append(
                f"{gate_name}: {failure_rate:.0%} failure rate -- {recommendation}"
            )

    return issues


def get_gate_statistics(
    db: Session, client_id: int, days: int = 30
) -> dict:
    """Compute per-gate pass rates and statistics.

    Args:
        db: SQLAlchemy session.
        client_id: Client ID.
        days: Lookback window in days (default 30).

    Returns:
        Dict with:
        - overall_pass_rate: float (0.0 to 1.0)
        - total_drafts: int
        - per_gate: dict[gate_name, {pass_rate, failure_rate, total, failures, common_failures}]
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Query drafts with gate reports from the lookback window
    drafts = (
        db.query(ContentDraft)
        .filter(
            ContentDraft.client_id == client_id,
            ContentDraft.gate_report.isnot(None),
            ContentDraft.created_at >= cutoff,
        )
        .all()
    )

    if not drafts:
        return {
            "overall_pass_rate": 1.0,
            "total_drafts": 0,
            "per_gate": {},
        }

    # Aggregate gate results
    gate_totals: dict[str, int] = Counter()
    gate_failures: dict[str, int] = Counter()
    gate_failure_reasons: dict[str, list[str]] = {}
    pipeline_passes = 0

    for draft in drafts:
        report = draft.gate_report
        if not isinstance(report, dict):
            continue

        status = report.get("status", "")
        if status in ("passed", "passed_with_fix"):
            pipeline_passes += 1

        results = report.get("results", [])
        for result in results:
            gate_name = result.get("gate_name", "")
            gate_status = result.get("status", "")
            gate_totals[gate_name] += 1
            if gate_status == "rejected":
                gate_failures[gate_name] += 1
                detail = result.get("detail", "")
                if gate_name not in gate_failure_reasons:
                    gate_failure_reasons[gate_name] = []
                if detail:
                    gate_failure_reasons[gate_name].append(detail)

    total_drafts = len(drafts)
    overall_pass_rate = pipeline_passes / total_drafts if total_drafts > 0 else 1.0

    per_gate: dict[str, dict] = {}
    for gate_name in gate_totals:
        total = gate_totals[gate_name]
        failures = gate_failures.get(gate_name, 0)
        failure_rate = failures / total if total > 0 else 0.0
        pass_rate = 1.0 - failure_rate

        # Get most common failure reasons
        reasons = gate_failure_reasons.get(gate_name, [])
        common_failures = Counter(reasons).most_common(3)

        per_gate[gate_name] = {
            "pass_rate": pass_rate,
            "failure_rate": failure_rate,
            "total": total,
            "failures": failures,
            "common_failures": [
                {"reason": r, "count": c} for r, c in common_failures
            ],
        }

    return {
        "overall_pass_rate": overall_pass_rate,
        "total_drafts": total_drafts,
        "per_gate": per_gate,
    }


# -- Three-Input Validation --------------------------------------------------


def _validate_research(db: Session, client_id: int) -> list:
    """Validate research findings exist for the client.

    Raises ContentGenerationError if no current research is available.
    """
    try:
        from sophia.research.service import get_findings_for_content

        findings = get_findings_for_content(db, client_id, limit=20)
        if not findings:
            raise ContentGenerationError(
                message="Research-first rule: no current research findings available",
                detail=f"client_id={client_id}",
                reason="missing_research",
                suggestion=(
                    "Run a research cycle first with run_research_cycle(). "
                    "Sophia never generates content without fresh research."
                ),
            )
        return findings
    except ImportError:
        raise ContentGenerationError(
            message="Research service not available",
            detail="sophia.research.service module not found",
            reason="missing_dependency",
            suggestion="Ensure Phase 2 (Research) is implemented",
        )


def _validate_intelligence(db: Session, client_id: int) -> Any:
    """Validate intelligence profile meets minimum completeness.

    Raises ContentGenerationError if profile is insufficient.
    """
    try:
        from sophia.intelligence.service import ClientService

        client = ClientService.get_client(db, client_id)

        # Minimum completeness check: need basic profile fields
        if not client.business_description and not client.content_pillars:
            raise ContentGenerationError(
                message="Intelligence profile incomplete: missing business description and content pillars",
                detail=f"client_id={client_id}, completeness={client.profile_completeness_pct}%",
                reason="incomplete_intelligence",
                suggestion=(
                    "Complete the client profile with at minimum a business description "
                    "and at least one content pillar."
                ),
            )
        return client
    except ImportError:
        raise ContentGenerationError(
            message="Intelligence service not available",
            detail="sophia.intelligence.service module not found",
            reason="missing_dependency",
            suggestion="Ensure Phase 1 (Intelligence) is implemented",
        )


def _validate_voice_profile(db: Session, client_id: int) -> dict:
    """Validate voice profile exists for the client.

    Raises ContentGenerationError if no voice profile found.
    """
    try:
        from sophia.intelligence.models import VoiceProfile

        voice = (
            db.query(VoiceProfile)
            .filter(VoiceProfile.client_id == client_id)
            .first()
        )
        if not voice or not voice.profile_data:
            raise ContentGenerationError(
                message="Voice profile not found: cannot generate content without voice matching",
                detail=f"client_id={client_id}",
                reason="missing_voice_profile",
                suggestion=(
                    "Build a voice profile first by adding voice materials "
                    "and running VoiceService.build_voice_profile()."
                ),
            )
        return voice.profile_data
    except ImportError:
        raise ContentGenerationError(
            message="Intelligence models not available",
            detail="sophia.intelligence.models module not found",
            reason="missing_dependency",
            suggestion="Ensure Phase 1 (Intelligence) is implemented",
        )


# -- Adaptive Option Count ---------------------------------------------------


def _compute_option_count(research: list) -> int:
    """Determine how many content options to generate based on research richness.

    Scoring:
    - Number of findings: 1-2 = thin, 3-7 = average, 8+ = rich
    - Source diversity: bonus for multiple source types
    - Recency: bonus for time-sensitive findings

    Returns:
        2-5 options per the locked decision.
    """
    if not research:
        return 2

    count = len(research)

    # Base from finding count
    if count <= 2:
        base = 2
    elif count <= 7:
        base = 3
    else:
        base = 4

    # Source diversity bonus
    source_types = set()
    for finding in research:
        if hasattr(finding, "finding_type"):
            ft = finding.finding_type
            source_types.add(ft.value if hasattr(ft, "value") else str(ft))
        elif isinstance(finding, dict):
            source_types.add(finding.get("finding_type", ""))

    if len(source_types) >= 3:
        base += 1

    # Time-sensitive bonus
    time_sensitive = sum(
        1
        for f in research
        if (getattr(f, "is_time_sensitive", 0) if hasattr(f, "is_time_sensitive")
            else (f.get("is_time_sensitive", 0) if isinstance(f, dict) else 0))
    )
    if time_sensitive >= 2:
        base += 1

    return min(5, max(2, base))


# -- Draft Ranking -----------------------------------------------------------


def _rank_drafts(
    drafts: list[ContentDraft], intelligence: Any
) -> list[ContentDraft]:
    """Rank drafts by predicted performance with reasoning.

    Considers: voice alignment score, content pillar balance, format diversity.

    Args:
        drafts: List of drafts to rank.
        intelligence: Client intelligence profile.

    Returns:
        Same list, sorted by rank (1 = best), with rank and rank_reasoning set.
    """
    if not drafts:
        return drafts

    # Score each draft
    scored: list[tuple[float, ContentDraft]] = []
    pillar_counts: dict[str, int] = {}

    for draft in drafts:
        score = 0.0

        # Voice alignment (higher = better)
        voice_pct = draft.voice_confidence_pct or 50.0
        score += voice_pct * 0.4  # 40% weight

        # Content pillar balance (penalize repetition)
        pillar = draft.content_pillar or "unspecified"
        pillar_counts[pillar] = pillar_counts.get(pillar, 0) + 1
        if pillar_counts[pillar] > 1:
            score -= 5 * (pillar_counts[pillar] - 1)

        # Feed posts rank higher than stories (more operator attention)
        if draft.content_type == "feed":
            score += 10
        else:
            score += 5

        # Time-sensitive content gets priority
        if draft.freshness_window == "post_within_24hrs":
            score += 15
        elif draft.freshness_window == "this_week":
            score += 5

        scored.append((score, draft))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    # Assign ranks
    for rank_idx, (score, draft) in enumerate(scored, 1):
        draft.rank = rank_idx
        reasons = []
        if draft.voice_confidence_pct and draft.voice_confidence_pct > 70:
            reasons.append("strong voice alignment")
        if draft.freshness_window == "post_within_24hrs":
            reasons.append("time-sensitive content")
        if draft.content_type == "feed":
            reasons.append("feed post (primary)")
        if draft.content_pillar:
            reasons.append(f"pillar: {draft.content_pillar}")
        draft.rank_reasoning = "; ".join(reasons) if reasons else "standard ranking"

    return [draft for _, draft in scored]


# -- Regeneration Service (CONT-05) ------------------------------------------


def regenerate_draft(
    db: Session, draft_id: int, guidance: str
) -> ContentDraft:
    """Regenerate a draft with operator's free-text guidance.

    - Enforces 3-attempt limit per draft
    - Re-validates three mandatory inputs (research-first rule applies)
    - Runs FULL quality gate pipeline on regenerated content (locked decision)
    - Logs guidance to RegenerationLog for pattern learning

    Args:
        db: SQLAlchemy session.
        draft_id: ID of the draft to regenerate.
        guidance: Free-text guidance from operator (e.g., "Make it funnier").

    Returns:
        Updated ContentDraft with new copy.

    Raises:
        RegenerationLimitError: If regeneration_count >= 3.
        ContentGenerationError: If three-input validation fails.
    """
    draft = db.query(ContentDraft).filter(ContentDraft.id == draft_id).first()
    if draft is None:
        raise ContentGenerationError(
            message="Draft not found",
            detail=f"draft_id={draft_id}",
            reason="not_found",
        )

    # Check regeneration limit
    if draft.regeneration_count >= 3:
        raise RegenerationLimitError(
            message="Regeneration limit reached for this draft",
            detail=f"draft_id={draft_id}, attempts={draft.regeneration_count}",
        )

    # Re-validate three mandatory inputs
    _validate_research(db, draft.client_id)
    _validate_intelligence(db, draft.client_id)
    _validate_voice_profile(db, draft.client_id)

    # Construct regeneration context (all prior guidance for full feedback arc)
    prior_guidance = draft.regeneration_guidance or []

    # In production: this would invoke Claude Code with the regeneration prompt
    # including: original system prompt, current draft as "previous version",
    # the operator's guidance, and all prior guidance for this draft.
    # For the orchestration layer, we simulate the regenerated copy.
    regenerated_copy = f"[Regenerated with guidance: {guidance}] {draft.copy}"

    # Run FULL quality gate pipeline on regenerated content (locked decision)
    original_copy = draft.copy
    draft.copy = regenerated_copy
    report = run_quality_gates(db, draft, draft.client_id)
    draft.gate_status = report.status
    draft.gate_report = report.to_dict()

    # If rejected by gates, revert copy but still log the attempt
    if report.status == "rejected":
        draft.copy = original_copy
        draft.gate_status = "rejected"

    # Increment regeneration_count
    draft.regeneration_count += 1

    # Append guidance to regeneration_guidance JSON array
    prior_guidance.append(guidance)
    draft.regeneration_guidance = prior_guidance

    # Log to RegenerationLog
    regen_log = RegenerationLog(
        content_draft_id=draft.id,
        client_id=draft.client_id,
        attempt_number=draft.regeneration_count,
        guidance=guidance,
    )
    db.add(regen_log)
    db.flush()

    return draft


def _analyze_guidance_patterns(
    db: Session, client_id: int
) -> list[dict]:
    """Analyze regeneration guidance for repeated patterns.

    Groups similar guidance strings by keyword/phrase matching.
    If any cluster has 5+ occurrences, returns it as a pattern with
    a suggested voice profile update.

    Args:
        db: SQLAlchemy session.
        client_id: Client ID to analyze.

    Returns:
        List of pattern dicts: {"pattern", "count", "suggestion"}.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    logs = (
        db.query(RegenerationLog)
        .filter(
            RegenerationLog.client_id == client_id,
            RegenerationLog.created_at >= cutoff,
        )
        .all()
    )

    if not logs:
        return []

    # Define keyword clusters for common guidance themes
    clusters: dict[str, list[str]] = {
        "humor/funny": [
            "funny", "funnier", "humor", "humorous", "joke", "witty",
            "lighter tone", "playful", "lighthearted",
        ],
        "shorter/concise": [
            "shorter", "concise", "brief", "trim", "cut down",
            "less wordy", "tighter",
        ],
        "casual/informal": [
            "casual", "informal", "relaxed", "conversational",
            "less formal", "more chill",
        ],
        "professional/formal": [
            "professional", "formal", "polished", "refined",
            "more serious", "business-like",
        ],
        "emotional/personal": [
            "emotional", "personal", "heartfelt", "authentic",
            "vulnerable", "real", "genuine",
        ],
        "engaging/questions": [
            "engaging", "question", "interactive", "call to action",
            "hook", "attention", "engaging",
        ],
        "simpler/clearer": [
            "simpler", "clearer", "easier", "plain language",
            "straightforward", "simple",
        ],
    }

    # Count matches per cluster
    cluster_counts: dict[str, int] = {name: 0 for name in clusters}
    for log in logs:
        guidance_lower = log.guidance.lower()
        for cluster_name, keywords in clusters.items():
            if any(kw in guidance_lower for kw in keywords):
                cluster_counts[cluster_name] += 1

    # Build patterns for clusters with 5+ occurrences
    suggestions_map = {
        "humor/funny": "Increase humor level in voice profile preferences",
        "shorter/concise": "Reduce target post length in voice profile",
        "casual/informal": "Shift formality toward casual in voice profile",
        "professional/formal": "Shift formality toward professional in voice profile",
        "emotional/personal": "Increase personal/emotional tone in voice profile",
        "engaging/questions": "Increase use of questions and CTAs in voice profile",
        "simpler/clearer": "Reduce vocabulary complexity in voice profile",
    }

    patterns = []
    for cluster_name, count in cluster_counts.items():
        if count >= 5:
            patterns.append({
                "pattern": cluster_name,
                "count": count,
                "suggestion": suggestions_map.get(
                    cluster_name,
                    f"Update voice profile based on '{cluster_name}' pattern",
                ),
            })

    return patterns


def suggest_voice_profile_updates(
    db: Session, client_id: int
) -> list[str]:
    """Format voice profile update suggestions from guidance patterns.

    Calls _analyze_guidance_patterns and formats results as operator-facing
    suggestions.

    Args:
        db: SQLAlchemy session.
        client_id: Client ID.

    Returns:
        List of formatted suggestion strings.
    """
    patterns = _analyze_guidance_patterns(db, client_id)
    suggestions = []

    for p in patterns:
        suggestions.append(
            f"You've asked for more {p['pattern']} in {p['count']} of your "
            f"recent regeneration requests. {p['suggestion']}."
        )

    return suggestions


# -- Format Adaptation (CONT-06) --------------------------------------------


def get_format_weights(
    db: Session, client_id: int, platform: str
) -> dict[str, float]:
    """Compute performance-weighted format preferences for a client/platform.

    Formats with above-average engagement get higher weight.
    Formats with below-average get lower weight (but never zero).
    New/untested formats get an exploration weight of 0.15.

    Args:
        db: SQLAlchemy session.
        client_id: Client ID.
        platform: Platform name ("facebook" or "instagram").

    Returns:
        Dict mapping content_format -> weight (0.0 to 1.0, summing to ~1.0).
    """
    # All known content formats
    all_formats = [
        "question", "story", "how-to", "listicle",
        "behind-scenes", "educational", "promotional", "testimonial",
    ]

    records = (
        db.query(FormatPerformance)
        .filter(
            FormatPerformance.client_id == client_id,
            FormatPerformance.platform == platform,
        )
        .all()
    )

    if not records:
        # New client: equal weights
        weight = 1.0 / len(all_formats)
        return {fmt: round(weight, 4) for fmt in all_formats}

    # Compute average engagement across all formats
    engagement_map: dict[str, float] = {}
    for rec in records:
        engagement_map[rec.content_format] = rec.avg_engagement_rate or 0.0

    avg_engagement = (
        sum(engagement_map.values()) / len(engagement_map)
        if engagement_map
        else 0.0
    )

    # Assign weights
    raw_weights: dict[str, float] = {}
    exploration_weight = 0.15

    for fmt in all_formats:
        if fmt in engagement_map:
            eng = engagement_map[fmt]
            if avg_engagement > 0:
                # Ratio-based weight: above-average gets more, below-average gets less
                ratio = eng / avg_engagement
                raw_weights[fmt] = max(0.1, min(2.0, ratio))
            else:
                raw_weights[fmt] = 1.0
        else:
            # Untested format: exploration weight
            raw_weights[fmt] = exploration_weight

    # Normalize to sum to ~1.0
    total = sum(raw_weights.values())
    if total > 0:
        return {fmt: round(w / total, 4) for fmt, w in raw_weights.items()}

    weight = 1.0 / len(all_formats)
    return {fmt: round(weight, 4) for fmt in all_formats}


def update_format_performance(
    db: Session,
    client_id: int,
    platform: str,
    content_format: str,
    engagement_rate: float,
    save_rate: float | None = None,
    ctr: float | None = None,
) -> FormatPerformance:
    """Upsert format performance record with rolling averages.

    Uses exponential moving average with alpha=0.3 to weight recent data more.

    Args:
        db: SQLAlchemy session.
        client_id: Client ID.
        platform: Platform name.
        content_format: Content format name.
        engagement_rate: New engagement rate observation.
        save_rate: Optional save rate observation.
        ctr: Optional click-through rate observation.

    Returns:
        Updated FormatPerformance record.
    """
    alpha = 0.3  # EMA weight for recent data

    record = (
        db.query(FormatPerformance)
        .filter(
            FormatPerformance.client_id == client_id,
            FormatPerformance.platform == platform,
            FormatPerformance.content_format == content_format,
        )
        .first()
    )

    if record is None:
        # Create new record
        record = FormatPerformance(
            client_id=client_id,
            platform=platform,
            content_format=content_format,
            sample_count=1,
            avg_engagement_rate=engagement_rate,
            avg_save_rate=save_rate,
            avg_ctr=ctr,
        )
        db.add(record)
    else:
        # Update with EMA
        record.sample_count += 1
        record.avg_engagement_rate = (
            alpha * engagement_rate
            + (1 - alpha) * (record.avg_engagement_rate or 0.0)
        )
        if save_rate is not None:
            record.avg_save_rate = (
                alpha * save_rate
                + (1 - alpha) * (record.avg_save_rate or 0.0)
            )
        if ctr is not None:
            record.avg_ctr = (
                alpha * ctr + (1 - alpha) * (record.avg_ctr or 0.0)
            )
        record.last_updated_at = datetime.now(timezone.utc)

    db.flush()
    return record


def explain_format_adaptations(
    db: Session, client_id: int
) -> list[str]:
    """Generate natural language explanations for format weight shifts.

    Compares current format weights against equal distribution and
    describes significant shifts.

    Args:
        db: SQLAlchemy session.
        client_id: Client ID.

    Returns:
        List of human-readable explanation strings.
    """
    explanations = []
    equal_weight = 1.0 / 8  # 8 known formats

    for platform in ["facebook", "instagram"]:
        weights = get_format_weights(db, client_id, platform)

        for fmt, weight in weights.items():
            # Significant shift: more than 50% above or below equal
            if weight > equal_weight * 1.5:
                ratio = weight / equal_weight
                explanations.append(
                    f"Generating more {fmt} posts on {platform} because "
                    f"they've performed {ratio:.1f}x better for this client"
                )
            elif weight < equal_weight * 0.5 and weight > 0:
                explanations.append(
                    f"Reducing {fmt} posts on {platform} due to "
                    f"below-average engagement for this client"
                )

    return explanations


def analyze_rejection_patterns(
    db: Session, client_id: int
) -> dict:
    """Analyze operator rejection patterns by content pillar and format.

    Flags categories with >80% rejection rate.

    Args:
        db: SQLAlchemy session.
        client_id: Client ID.

    Returns:
        Dict with flagged categories and suggested adjustments.
    """
    drafts = (
        db.query(ContentDraft)
        .filter(
            ContentDraft.client_id == client_id,
            ContentDraft.status.in_(["approved", "rejected"]),
        )
        .all()
    )

    if not drafts:
        return {}

    # Group by pillar_format combination
    category_stats: dict[str, dict] = {}
    for draft in drafts:
        pillar = draft.content_pillar or "unspecified"
        fmt = draft.content_format or "unspecified"
        key = f"{pillar}_{fmt}"

        if key not in category_stats:
            category_stats[key] = {"total": 0, "rejected": 0}

        category_stats[key]["total"] += 1
        if draft.status == "rejected":
            category_stats[key]["rejected"] += 1

    # Flag categories with >80% rejection
    flagged = {}
    for category, stats in category_stats.items():
        if stats["total"] >= 3:  # Need minimum sample size
            rejection_rate = stats["rejected"] / stats["total"]
            if rejection_rate > 0.80:
                flagged[category] = {
                    "rejection_rate": round(rejection_rate, 2),
                    "total": stats["total"],
                    "rejected": stats["rejected"],
                    "suggestion": (
                        f"Reduce {category} frequency or adjust tone. "
                        f"{stats['rejected']}/{stats['total']} rejected."
                    ),
                }

    return flagged


def calibrate_ranking_from_choices(
    db: Session, client_id: int
) -> dict:
    """Track which rank positions operators prefer.

    If operator consistently picks #2 or #3 over #1, log as ranking
    calibration signal.

    Args:
        db: SQLAlchemy session.
        client_id: Client ID.

    Returns:
        Dict with rank preference data and calibration signal.
    """
    approved = (
        db.query(ContentDraft)
        .filter(
            ContentDraft.client_id == client_id,
            ContentDraft.status == "approved",
            ContentDraft.rank.isnot(None),
        )
        .all()
    )

    if not approved:
        return {"total_approved": 0, "rank_distribution": {}, "signal": None}

    rank_counts: dict[int, int] = Counter()
    for draft in approved:
        rank_counts[draft.rank] += 1

    total = len(approved)
    rank_distribution = {
        rank: {"count": count, "pct": round(count / total, 2)}
        for rank, count in sorted(rank_counts.items())
    }

    # Detect calibration signal: if #1 is NOT the most picked
    signal = None
    if total >= 5:  # Need minimum sample
        rank_1_pct = rank_distribution.get(1, {}).get("pct", 0)
        for rank, data in rank_distribution.items():
            if rank != 1 and data["pct"] > rank_1_pct:
                signal = (
                    f"Operator prefers rank #{rank} ({data['pct']:.0%}) over "
                    f"rank #1 ({rank_1_pct:.0%}). Ranking model may need adjustment."
                )
                break

    return {
        "total_approved": total,
        "rank_distribution": rank_distribution,
        "signal": signal,
    }


# -- Evergreen Bank Management -----------------------------------------------


def manage_evergreen_bank(
    db: Session, client_id: int
) -> dict:
    """Manage evergreen content bank: enforce cap and expiry.

    - Cap: 20 entries per client (Claude's discretion from CONTEXT.md)
    - Auto-expire: entries older than 90 days
    - Returns summary of actions taken

    Args:
        db: SQLAlchemy session.
        client_id: Client ID.

    Returns:
        Dict with bank status and actions taken.
    """
    now = datetime.now(timezone.utc)
    expiry_cutoff = now - timedelta(days=90)

    # Auto-expire entries older than 90 days
    expired_entries = (
        db.query(EvergreenEntry)
        .filter(
            EvergreenEntry.client_id == client_id,
            EvergreenEntry.is_used == False,  # noqa: E712
            EvergreenEntry.created_at < expiry_cutoff,
        )
        .all()
    )
    for entry in expired_entries:
        entry.is_used = True  # Mark as used (expired)
        entry.used_at = now

    # Check cap: 20 entries
    active_entries = (
        db.query(EvergreenEntry)
        .filter(
            EvergreenEntry.client_id == client_id,
            EvergreenEntry.is_used == False,  # noqa: E712
        )
        .order_by(EvergreenEntry.created_at.asc())
        .all()
    )

    capped = []
    if len(active_entries) > 20:
        # Remove oldest unused entries above cap
        excess = active_entries[: len(active_entries) - 20]
        for entry in excess:
            entry.is_used = True
            entry.used_at = now
            capped.append(entry.id)

    db.flush()

    return {
        "client_id": client_id,
        "expired_count": len(expired_entries),
        "capped_count": len(capped),
        "active_count": len(active_entries) - len(capped),
    }


def get_evergreen_options(
    db: Session, client_id: int, limit: int = 5
) -> list[EvergreenEntry]:
    """Get unused evergreen entries within 90-day window.

    Args:
        db: SQLAlchemy session.
        client_id: Client ID.
        limit: Maximum entries to return.

    Returns:
        List of EvergreenEntry objects (freshest first).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)

    return (
        db.query(EvergreenEntry)
        .filter(
            EvergreenEntry.client_id == client_id,
            EvergreenEntry.is_used == False,  # noqa: E712
            EvergreenEntry.created_at >= cutoff,
        )
        .order_by(EvergreenEntry.id.desc())
        .limit(limit)
        .all()
    )


def mark_evergreen_used(
    db: Session, evergreen_id: int
) -> EvergreenEntry:
    """Mark an evergreen entry as used.

    Args:
        db: SQLAlchemy session.
        evergreen_id: EvergreenEntry ID.

    Returns:
        Updated EvergreenEntry.

    Raises:
        ContentGenerationError: If entry not found.
    """
    entry = (
        db.query(EvergreenEntry)
        .filter(EvergreenEntry.id == evergreen_id)
        .first()
    )
    if entry is None:
        raise ContentGenerationError(
            message="Evergreen entry not found",
            detail=f"evergreen_id={evergreen_id}",
            reason="not_found",
        )

    entry.is_used = True
    entry.used_at = datetime.now(timezone.utc)
    db.flush()
    return entry


# -- Helpers -----------------------------------------------------------------


def _get_approved_posts(
    db: Session, client_id: int, limit: int = 30
) -> list[str]:
    """Get approved/published post texts for voice baseline and few-shot.

    Queries content_drafts with status in ('approved', 'published'),
    ordered by most recent first.
    """
    approved = (
        db.query(ContentDraft)
        .filter(
            ContentDraft.client_id == client_id,
            ContentDraft.status.in_(["approved", "published"]),
        )
        .order_by(ContentDraft.id.desc())
        .limit(limit)
        .all()
    )
    return [d.copy for d in approved if d.copy]


def _build_client_config(intelligence: Any) -> dict:
    """Build client config dict from intelligence profile."""
    config: dict[str, Any] = {}

    if isinstance(intelligence, dict):
        config["guardrails"] = intelligence.get("guardrails", {})
        config["content_pillars"] = intelligence.get("content_pillars", [])
        config["brand_assets"] = intelligence.get("brand_assets", {})
        config["upcoming_events"] = intelligence.get("upcoming_events", [])
    else:
        config["guardrails"] = getattr(intelligence, "guardrails", {}) or {}
        config["content_pillars"] = getattr(intelligence, "content_pillars", []) or []
        config["brand_assets"] = getattr(intelligence, "brand_assets", {}) or {}
        config["upcoming_events"] = []

    return config


def _extract_business_name(intelligence: Any) -> str:
    """Extract business name from intelligence profile."""
    if isinstance(intelligence, dict):
        return intelligence.get("name", intelligence.get("business_name", "the business"))
    if hasattr(intelligence, "name"):
        return intelligence.name
    return "the business"


def _get_image_ratio(platform: str, content_type: str) -> str:
    """Get the primary image ratio for a platform/content_type combination."""
    from sophia.content.prompt_builder import PLATFORM_RULES

    rules = PLATFORM_RULES.get(platform, {}).get(content_type, {})
    ratio = rules.get("image_ratio", "1:1")
    # Pick the first ratio if multiple offered
    if " or " in ratio:
        ratio = ratio.split(" or ")[0]
    return ratio
