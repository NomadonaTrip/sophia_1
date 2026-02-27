"""Content generation orchestrator: three-input validation, batch generation,
voice alignment integration, ranking, and persistence.

This is Sophia's primary value delivery -- generating content that sounds like
the client, is grounded in real research, and is platform-optimized.

The orchestrator enforces the research-first rule: no content is generated
without all three mandatory inputs (research, intelligence, voice profile).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from sophia.content.models import ContentDraft, EvergreenEntry
from sophia.content.prompt_builder import (
    build_batch_prompts,
    build_image_prompt,
)
from sophia.content.voice_alignment import (
    compute_voice_baseline,
    compute_voice_confidence,
    score_voice_alignment,
)
from sophia.exceptions import ContentGenerationError

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

    # Step 7: Rank drafts
    drafts = _rank_drafts(drafts, intelligence)

    # Step 8: Persist to database
    for draft in drafts:
        db.add(draft)
    db.flush()

    # Save evergreen drafts to bank
    for draft in drafts:
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
    for draft in drafts:
        db.refresh(draft)

    return drafts


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
