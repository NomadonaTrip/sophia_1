"""Four-dimension capability evaluation rubric.

Scores discovered capabilities on: relevance (0.30), quality (0.25),
security (0.25), and fit (0.20). Auto-rejects if any dimension falls
below 3. Assigns recommendation tiers: recommend / neutral / caution.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field

from sophia.capabilities.search import DiscoveredCapabilityData

# -- Rubric configuration -----------------------------------------------------

DIMENSION_WEIGHTS: dict[str, float] = {
    "relevance": 0.30,
    "quality": 0.25,
    "security": 0.25,
    "fit": 0.20,
}

AUTO_REJECT_THRESHOLD = 3  # Any dimension below this triggers auto-reject


# -- Scoring models -----------------------------------------------------------


class RubricScore(BaseModel):
    """Score for a single rubric dimension with justification."""

    dimension: str
    score: int = Field(ge=0, le=5)
    justification: str


class EvaluationResult(BaseModel):
    """Full evaluation result with composite score and recommendation."""

    scores: list[RubricScore]
    composite_score: float
    recommendation: str  # "recommend", "neutral", "caution"
    auto_rejected: bool
    rejection_reason: str | None = None


# -- Core evaluation logic ----------------------------------------------------


def evaluate_capability(scores: list[RubricScore]) -> EvaluationResult:
    """Evaluate a capability based on rubric dimension scores.

    1. Check auto-reject: if ANY dimension < 3, auto-reject.
    2. Calculate weighted composite score.
    3. Determine recommendation tier based on composite.

    Returns EvaluationResult with all details.
    """
    # Check auto-reject
    auto_rejected = False
    rejection_reason = None

    for score in scores:
        if score.score < AUTO_REJECT_THRESHOLD:
            auto_rejected = True
            rejection_reason = (
                f"Auto-rejected: '{score.dimension}' scored {score.score}/5 "
                f"(below minimum threshold of {AUTO_REJECT_THRESHOLD})"
            )
            break

    # Calculate weighted composite
    composite = 0.0
    for score in scores:
        weight = DIMENSION_WEIGHTS.get(score.dimension, 0.0)
        composite += score.score * weight

    # Determine recommendation tier
    if composite >= 4.0:
        recommendation = "recommend"
    elif composite >= 3.0:
        recommendation = "neutral"
    else:
        recommendation = "caution"

    return EvaluationResult(
        scores=scores,
        composite_score=round(composite, 2),
        recommendation=recommendation,
        auto_rejected=auto_rejected,
        rejection_reason=rejection_reason,
    )


# -- Heuristic scoring --------------------------------------------------------

# Stack keywords for fit scoring
STACK_KEYWORDS = {
    "python",
    "fastapi",
    "sqlite",
    "sqlalchemy",
    "mcp",
    "claude",
    "pydantic",
}


def score_discovered_capability(
    capability: DiscoveredCapabilityData,
    gap_description: str = "",
) -> list[RubricScore]:
    """Score a discovered capability using heuristics.

    Heuristic-based scoring using available metadata. In production,
    Claude will replace this with LLM-based deeper analysis.

    Dimensions:
    - Relevance: keyword overlap between capability and gap descriptions
    - Quality: GitHub stars, recent update activity
    - Security: source trust (MCP Registry > GitHub), community size
    - Fit: stack keyword matching (python, fastapi, sqlite, etc.)
    """
    scores: list[RubricScore] = []

    # -- Relevance scoring (keyword overlap with gap description) --
    relevance = _score_relevance(capability, gap_description)
    scores.append(relevance)

    # -- Quality scoring (stars, maintenance activity) --
    quality = _score_quality(capability)
    scores.append(quality)

    # -- Security scoring (source trust, community signals) --
    security = _score_security(capability)
    scores.append(security)

    # -- Fit scoring (stack compatibility) --
    fit = _score_fit(capability)
    scores.append(fit)

    return scores


def _score_relevance(
    capability: DiscoveredCapabilityData, gap_description: str
) -> RubricScore:
    """Score relevance via keyword overlap between capability and gap."""
    cap_text = f"{capability.name} {capability.description}".lower()
    gap_words = set(
        re.findall(r"\b[a-z]{3,}\b", gap_description.lower())
    )

    if not gap_words:
        return RubricScore(
            dimension="relevance",
            score=3,
            justification="No gap description provided for comparison; default neutral score",
        )

    overlap = sum(1 for w in gap_words if w in cap_text)
    ratio = overlap / len(gap_words) if gap_words else 0

    if ratio >= 0.5:
        score = 5
        justification = f"Strong keyword match: {overlap}/{len(gap_words)} gap keywords found in capability"
    elif ratio >= 0.3:
        score = 4
        justification = f"Good keyword match: {overlap}/{len(gap_words)} gap keywords found"
    elif ratio >= 0.15:
        score = 3
        justification = f"Moderate keyword match: {overlap}/{len(gap_words)} gap keywords found"
    elif ratio > 0:
        score = 2
        justification = f"Weak keyword match: only {overlap}/{len(gap_words)} gap keywords found"
    else:
        score = 1
        justification = "No keyword overlap between capability and gap description"

    return RubricScore(dimension="relevance", score=score, justification=justification)


def _score_quality(capability: DiscoveredCapabilityData) -> RubricScore:
    """Score quality based on stars and update recency."""
    stars = capability.stars or 0
    justifications: list[str] = []

    # Star-based scoring
    if stars > 100:
        score = 5
        justifications.append(f"{stars} stars (excellent community adoption)")
    elif stars > 50:
        score = 4
        justifications.append(f"{stars} stars (good community adoption)")
    elif stars > 10:
        score = 3
        justifications.append(f"{stars} stars (moderate adoption)")
    elif stars > 0:
        score = 2
        justifications.append(f"{stars} stars (low adoption)")
    else:
        score = 1
        justifications.append("No star data available")

    # Recency bonus: updated within 3 months gets +1 (capped at 5)
    if capability.last_updated:
        now = datetime.now(timezone.utc)
        last_updated_aware = capability.last_updated
        if last_updated_aware.tzinfo is None:
            last_updated_aware = last_updated_aware.replace(tzinfo=timezone.utc)
        age = now - last_updated_aware
        if age <= timedelta(days=90):
            score = min(score + 1, 5)
            justifications.append("Recently updated (within 3 months)")
        elif age > timedelta(days=365):
            justifications.append("Not updated in over a year")

    return RubricScore(
        dimension="quality",
        score=score,
        justification="; ".join(justifications),
    )


def _score_security(capability: DiscoveredCapabilityData) -> RubricScore:
    """Score security based on source trust and community signals."""
    if capability.source == "mcp_registry":
        score = 4
        justification = "From MCP Registry (vetted listing)"
    elif capability.source == "github":
        stars = capability.stars or 0
        if stars > 50:
            score = 3
            justification = f"GitHub repo with {stars} stars (community-validated)"
        elif stars > 10:
            score = 3
            justification = f"GitHub repo with {stars} stars (some community validation)"
        else:
            score = 2
            justification = f"GitHub repo with {stars} stars (limited community validation)"
    else:
        score = 2
        justification = "Unknown source -- limited trust signals"

    return RubricScore(
        dimension="security", score=score, justification=justification
    )


def _score_fit(capability: DiscoveredCapabilityData) -> RubricScore:
    """Score fit by checking stack keyword matches in capability text."""
    cap_text = f"{capability.name} {capability.description}".lower()

    matches = [kw for kw in STACK_KEYWORDS if kw in cap_text]
    match_count = len(matches)

    if match_count >= 3:
        score = 5
        justification = f"Excellent stack fit: matches {', '.join(matches)}"
    elif match_count >= 2:
        score = 4
        justification = f"Good stack fit: matches {', '.join(matches)}"
    elif match_count >= 1:
        score = 3
        justification = f"Partial stack fit: matches {', '.join(matches)}"
    else:
        score = 2
        justification = "No stack keyword matches detected"

    return RubricScore(dimension="fit", score=score, justification=justification)
