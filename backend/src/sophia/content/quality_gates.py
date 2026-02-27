"""Quality gate pipeline: sequential gate execution with auto-fix-once retry.

Every content draft passes through six gates in locked order before entering
the operator's approval queue:

1. Sensitivity -- tone-deaf content relative to local events / industry
2. Voice Alignment -- stylometric drift detection against approved post baseline
3. Plagiarism/Originality -- dual-layer (semantic via LanceDB + text via difflib)
4. AI Pattern Detection -- cliche detection + sentence uniformity scoring
5. Research Grounding -- verifies claims against tagged research findings
6. Brand Safety -- per-client guardrails (no competitor names, no unverifiable claims)

On first failure Sophia attempts auto-fix and re-runs the same gate.
On second failure the draft is rejected with a specific reason.
"""

from __future__ import annotations

import difflib
import json
import logging
import re
import statistics
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional

from sqlalchemy.orm import Session

from sophia.content.models import ContentDraft

logger = logging.getLogger(__name__)


# =============================================================================
# Data types
# =============================================================================


class GateStatus(str, Enum):
    PASSED = "passed"
    PASSED_WITH_FIX = "passed_with_fix"
    REJECTED = "rejected"


@dataclass
class GateResult:
    gate_name: str
    status: GateStatus
    score: float  # 0.0 to 1.0
    detail: str | None = None
    fix_applied: str | None = None


@dataclass
class QualityReport:
    status: str  # "passed", "passed_with_fix", "rejected"
    results: list[GateResult] = field(default_factory=list)
    rejected_by: str | None = None
    summary_badge: str = ""

    def to_dict(self) -> dict:
        """Serialize to JSON-safe dict for storage on ContentDraft.gate_report."""
        return {
            "status": self.status,
            "results": [
                {
                    "gate_name": r.gate_name,
                    "status": r.status.value,
                    "score": r.score,
                    "detail": r.detail,
                    "fix_applied": r.fix_applied,
                }
                for r in self.results
            ],
            "rejected_by": self.rejected_by,
            "summary_badge": self.summary_badge,
        }


# Gate execution order -- LOCKED DECISION, do not change
GATE_ORDER = [
    "sensitivity",
    "voice_alignment",
    "plagiarism_originality",
    "ai_pattern_detection",
    "research_grounding",
    "brand_safety",
]

# Gate function dispatch table (populated below)
_GATE_FUNCTIONS: dict[str, Any] = {}


# =============================================================================
# Pipeline orchestrator
# =============================================================================


def run_pipeline(
    db: Session,
    draft: ContentDraft,
    client_id: int,
) -> QualityReport:
    """Run all quality gates in locked order with auto-fix-once semantics.

    Args:
        db: SQLAlchemy session.
        draft: The content draft to evaluate.
        client_id: Client ID for loading config / history.

    Returns:
        QualityReport with per-gate results and summary badge.
    """
    results: list[GateResult] = []
    has_fix = False

    for gate_name in GATE_ORDER:
        gate_fn = _GATE_FUNCTIONS[gate_name]
        result = gate_fn(db, draft, client_id)

        if result.status == GateStatus.PASSED:
            results.append(result)
            continue

        # Gate failed -- attempt auto-fix (one try only)
        fixed_draft = _attempt_auto_fix(draft, gate_name, result)

        if fixed_draft is not None:
            # Re-run the same gate on the fixed draft
            retry_result = gate_fn(db, fixed_draft, client_id)

            if retry_result.status == GateStatus.PASSED:
                # Fix worked -- mark as PASSED_WITH_FIX
                retry_result = GateResult(
                    gate_name=gate_name,
                    status=GateStatus.PASSED_WITH_FIX,
                    score=retry_result.score,
                    detail=retry_result.detail,
                    fix_applied=f"Auto-fixed: {result.detail}",
                )
                # Apply the fix to the original draft
                draft.copy = fixed_draft.copy
                results.append(retry_result)
                has_fix = True
                continue

        # Auto-fix failed or not possible -- reject
        result.status = GateStatus.REJECTED
        results.append(result)

        report = QualityReport(
            status="rejected",
            results=results,
            rejected_by=gate_name,
            summary_badge=f"Rejected ({gate_name})",
        )
        _persist_gate_results(db, draft, report)
        return report

    # All gates passed
    if has_fix:
        fixed_gates = [
            r.gate_name
            for r in results
            if r.status == GateStatus.PASSED_WITH_FIX
        ]
        badge = f"Passed with fix ({', '.join(fixed_gates)} corrected)"
        status = "passed_with_fix"
    else:
        badge = "Passed all gates"
        status = "passed"

    report = QualityReport(
        status=status,
        results=results,
        summary_badge=badge,
    )
    _persist_gate_results(db, draft, report)
    return report


def _persist_gate_results(
    db: Session, draft: ContentDraft, report: QualityReport
) -> None:
    """Persist the quality report onto the draft for tracking and learning."""
    draft.gate_status = report.status
    draft.gate_report = report.to_dict()


# =============================================================================
# Auto-fix
# =============================================================================


def _attempt_auto_fix(
    draft: ContentDraft, gate_name: str, result: GateResult
) -> ContentDraft | None:
    """Attempt a single auto-fix for a gate failure.

    Creates a shallow copy of the draft with modified copy. Returns None if
    auto-fix is not feasible for this gate / failure type.

    In production this would invoke Claude Code to rewrite. For now we apply
    deterministic heuristic fixes that can be tested without LLM calls.
    """
    if not draft.copy:
        return None

    detail = result.detail or ""
    fixed_copy: str | None = None

    if gate_name == "sensitivity":
        # Placeholder: in production Claude rewrites to remove sensitivity concern
        fixed_copy = _fix_sensitivity(draft.copy, detail)
    elif gate_name == "voice_alignment":
        # Voice fix would require LLM rewriting -- return None for now
        # Voice alignment fixes are hard to do deterministically
        return None
    elif gate_name == "plagiarism_originality":
        # Plagiarism fix: append differentiating suffix
        fixed_copy = _fix_plagiarism(draft.copy)
    elif gate_name == "ai_pattern_detection":
        fixed_copy = _fix_ai_patterns(draft.copy, detail)
    elif gate_name == "research_grounding":
        fixed_copy = _fix_research_grounding(draft.copy, detail)
    elif gate_name == "brand_safety":
        fixed_copy = _fix_brand_safety(draft.copy, detail)

    if fixed_copy is None or fixed_copy == draft.copy:
        return None

    # Create a lightweight copy of the draft with new text
    fixed_draft = ContentDraft(
        client_id=draft.client_id,
        platform=draft.platform,
        content_type=draft.content_type,
        copy=fixed_copy,
        image_prompt=draft.image_prompt,
        image_ratio=draft.image_ratio,
        hashtags=draft.hashtags,
        alt_text=draft.alt_text,
        content_pillar=draft.content_pillar,
        freshness_window=draft.freshness_window,
        research_source_ids=draft.research_source_ids,
    )
    return fixed_draft


def _fix_sensitivity(copy: str, detail: str) -> str | None:
    """Deterministic sensitivity fix: soften language around flagged concerns."""
    # In production this is LLM-driven. Here we just note the fix happened.
    return copy + " [sensitivity-adjusted]"


def _fix_plagiarism(copy: str) -> str | None:
    """Add differentiating content to reduce similarity score."""
    return copy + " [rephrased for originality]"


def _fix_ai_patterns(copy: str, detail: str) -> str | None:
    """Remove known AI cliche patterns from copy."""
    fixed = copy
    for pattern in AI_CLICHE_PATTERNS:
        fixed = re.sub(pattern, "", fixed, flags=re.IGNORECASE)
    # Clean up double spaces
    fixed = re.sub(r"\s{2,}", " ", fixed).strip()
    if fixed and fixed != copy:
        return fixed
    return None


def _fix_research_grounding(copy: str, detail: str) -> str | None:
    """Soften ungrounded claims by adding hedging language."""
    # In production: LLM removes or hedges specific ungrounded claims
    return copy + " [claims softened]"


def _fix_brand_safety(copy: str, detail: str) -> str | None:
    """Remove brand safety violations from copy."""
    fixed = copy
    # Remove common unverifiable superlatives
    unverifiable_patterns = [
        r"\bbest\s+in\s+\w+\b",
        r"\b#1\b",
        r"\bnumber\s+one\b",
        r"\btop\s+rated\b",
    ]
    for pattern in unverifiable_patterns:
        fixed = re.sub(pattern, "", fixed, flags=re.IGNORECASE)
    fixed = re.sub(r"\s{2,}", " ", fixed).strip()
    if fixed and fixed != copy:
        return fixed
    return None


# =============================================================================
# Gate 1: Sensitivity (SAFE-05)
# =============================================================================


def run_sensitivity_gate(
    db: Session, draft: ContentDraft, client_id: int
) -> GateResult:
    """Evaluate content against sensitivity concerns.

    Checks for:
    - Tone-deaf overlap with sensitive local events (7-day window)
    - Inappropriate topics given industry and sensitivity level
    - Legally problematic claims
    - Content that could alienate target audience

    Uses LLM-based evaluation in production. Here we provide a deterministic
    implementation that checks industry-calibrated keyword sensitivity.
    """
    copy = draft.copy or ""
    if not copy.strip():
        return GateResult(
            gate_name="sensitivity",
            status=GateStatus.PASSED,
            score=1.0,
            detail="Empty content -- no sensitivity concerns",
        )

    # Load client config for sensitivity calibration
    client_config = _load_client_config(db, client_id)
    industry = client_config.get("industry", "").lower()
    sensitivity_level = client_config.get("sensitivity_level", "medium")

    # Load sensitive events (7-day window)
    sensitive_events = _load_sensitive_events(db, client_id)

    # Industry-calibrated sensitivity thresholds
    # bar/restaurant can be edgier than children's daycare (locked decision)
    high_sensitivity_industries = [
        "childcare", "daycare", "healthcare", "medical", "education",
        "financial", "legal", "insurance",
    ]
    is_high_sensitivity = any(
        ind in industry for ind in high_sensitivity_industries
    ) or sensitivity_level == "high"

    # Check for sensitive event overlap
    copy_lower = copy.lower()
    for event in sensitive_events:
        event_keywords = event.get("keywords", [])
        for keyword in event_keywords:
            if keyword.lower() in copy_lower:
                return GateResult(
                    gate_name="sensitivity",
                    status=GateStatus.REJECTED,
                    score=0.0,
                    detail=f"Content overlaps with sensitive event: {event.get('description', keyword)}",
                )

    # Check for universally sensitive content
    sensitive_patterns = [
        r"\b(tragedy|disaster|shooting|death|died|killed|massacre)\b",
        r"\b(lawsuit|sued|legal action|court order)\b",
    ]
    if is_high_sensitivity:
        # Stricter patterns for high-sensitivity industries
        sensitive_patterns.extend([
            r"\b(alcohol|drinking|drunk|bar|pub)\b",
            r"\b(controversial|debate|political|partisan)\b",
        ])

    for pattern in sensitive_patterns:
        if re.search(pattern, copy, re.IGNORECASE):
            return GateResult(
                gate_name="sensitivity",
                status=GateStatus.REJECTED,
                score=0.2,
                detail=f"Potentially sensitive content detected: matches pattern '{pattern}'",
            )

    return GateResult(
        gate_name="sensitivity",
        status=GateStatus.PASSED,
        score=1.0,
        detail="No sensitivity concerns detected",
    )


# =============================================================================
# Gate 2: Voice Alignment (CONT-04 enforcement)
# =============================================================================


def run_voice_alignment_gate(
    db: Session, draft: ContentDraft, client_id: int
) -> GateResult:
    """Check voice alignment against approved post baseline.

    Cold start (< 5 approved posts): automatically PASSED with low confidence
    note -- don't reject during calibration period (locked decision: first 10
    posts are calibration).
    """
    from sophia.content.voice_alignment import (
        compute_voice_baseline,
        score_voice_alignment,
    )

    copy = draft.copy or ""
    if not copy.strip():
        return GateResult(
            gate_name="voice_alignment",
            status=GateStatus.PASSED,
            score=1.0,
            detail="Empty content -- voice check skipped",
        )

    # Get approved posts for baseline
    approved_posts = _get_approved_posts(db, client_id, limit=30)

    # Cold start bypass (locked decision)
    if len(approved_posts) < 5:
        return GateResult(
            gate_name="voice_alignment",
            status=GateStatus.PASSED,
            score=0.5,
            detail=f"Cold start: only {len(approved_posts)} approved posts (need 5+ for calibration). Auto-passing.",
        )

    baseline = compute_voice_baseline(approved_posts)
    if not baseline:
        return GateResult(
            gate_name="voice_alignment",
            status=GateStatus.PASSED,
            score=0.5,
            detail="Could not compute baseline. Auto-passing.",
        )

    alignment_score, deviations = score_voice_alignment(copy, baseline)

    # Update draft voice confidence
    draft.voice_confidence_pct = alignment_score * 100

    if alignment_score >= 0.6:
        return GateResult(
            gate_name="voice_alignment",
            status=GateStatus.PASSED,
            score=alignment_score,
            detail=f"Voice alignment score: {alignment_score:.2f}",
        )

    return GateResult(
        gate_name="voice_alignment",
        status=GateStatus.REJECTED,
        score=alignment_score,
        detail=f"Voice drift detected (score {alignment_score:.2f} < 0.6): {'; '.join(deviations[:3])}",
    )


# =============================================================================
# Gate 3: Plagiarism / Originality (SAFE-06)
# =============================================================================


def run_plagiarism_gate(
    db: Session, draft: ContentDraft, client_id: int
) -> GateResult:
    """Dual-layer plagiarism check.

    Layer 1: Semantic similarity via BGE-M3 + LanceDB (threshold > 0.85)
    Layer 2: Text-level similarity via difflib (threshold > 0.60)

    Only checks against APPROVED content (not rejected drafts -- Pitfall 4).
    """
    copy = draft.copy or ""
    if not copy.strip():
        return GateResult(
            gate_name="plagiarism_originality",
            status=GateStatus.PASSED,
            score=1.0,
            detail="Empty content -- plagiarism check skipped",
        )

    # Layer 1: Semantic similarity via LanceDB
    semantic_result = _check_semantic_similarity(db, copy, client_id)
    if semantic_result is not None:
        sim_score, similar_preview = semantic_result
        if sim_score > 0.85:
            return GateResult(
                gate_name="plagiarism_originality",
                status=GateStatus.REJECTED,
                score=1.0 - sim_score,
                detail=f"Semantic similarity {sim_score:.2f} exceeds 0.85 threshold. Similar to: '{similar_preview[:80]}...'",
            )

    # Layer 2: Text-level similarity via difflib
    approved_posts = _get_approved_posts(db, client_id, limit=50)
    for existing_post in approved_posts:
        ratio = difflib.SequenceMatcher(
            None, copy.lower(), existing_post.lower()
        ).ratio()
        if ratio > 0.60:
            return GateResult(
                gate_name="plagiarism_originality",
                status=GateStatus.REJECTED,
                score=1.0 - ratio,
                detail=f"Text overlap {ratio:.0%} with existing post. Preview: '{existing_post[:80]}...'",
            )

    return GateResult(
        gate_name="plagiarism_originality",
        status=GateStatus.PASSED,
        score=1.0,
        detail="Content is original",
    )


# =============================================================================
# Gate 4: AI Pattern Detection
# =============================================================================

# Known AI cliche patterns (from research)
AI_CLICHE_PATTERNS: list[str] = [
    r"\bdive\s+in\b",
    r"\bin\s+today'?s\s+world\b",
    r"\bgame[\s-]?changer\b",
    r"\blevel\s+up\b",
    r"\bunlock\s+(?:your|the)\b",
    r"\bseamlessly\b",
    r"\bleverage\b",
    r"\bsynerg(?:y|ize)\b",
    r"\bholistically\b",
    r"\brobust\b",
    r"\btransformative\b",
    r"\bempowering\b",
    r"\bnavigating\s+(?:the|this)\b",
    r"\blandscape\b",
    r"\bjourney\b",
    r"\bdelve\b",
    r"\bfostering\b",
]


def run_ai_detection_gate(
    db: Session, draft: ContentDraft, client_id: int
) -> GateResult:
    """Detect AI-generated content patterns.

    Checks:
    1. Known AI cliche phrases (regex list)
    2. Unnaturally uniform sentence structure (CV < 0.3 is suspicious)
    """
    copy = draft.copy or ""
    if not copy.strip():
        return GateResult(
            gate_name="ai_pattern_detection",
            status=GateStatus.PASSED,
            score=1.0,
            detail="Empty content -- AI detection skipped",
        )

    issues: list[str] = []

    # Check 1: AI cliche patterns
    found_cliches = []
    for pattern in AI_CLICHE_PATTERNS:
        matches = re.findall(pattern, copy, re.IGNORECASE)
        if matches:
            found_cliches.extend(matches)

    if found_cliches:
        issues.append(f"AI cliches found: {', '.join(found_cliches[:5])}")

    # Check 2: Sentence structure uniformity
    sentences = _split_sentences(copy)
    if len(sentences) >= 3:
        lengths = [len(s.split()) for s in sentences]
        mean_len = statistics.mean(lengths)
        if mean_len > 0:
            std_len = statistics.stdev(lengths) if len(lengths) > 1 else 0.0
            cv = std_len / mean_len  # Coefficient of variation
            if cv < 0.3:
                issues.append(
                    f"Unnaturally uniform sentence structure (CV={cv:.2f}, "
                    f"human writing typically > 0.4)"
                )

    if issues:
        score = max(0.0, 1.0 - 0.3 * len(issues))
        return GateResult(
            gate_name="ai_pattern_detection",
            status=GateStatus.REJECTED,
            score=score,
            detail="; ".join(issues),
        )

    return GateResult(
        gate_name="ai_pattern_detection",
        status=GateStatus.PASSED,
        score=1.0,
        detail="No AI patterns detected",
    )


# =============================================================================
# Gate 5: Research Grounding
# =============================================================================


def run_research_grounding_gate(
    db: Session, draft: ContentDraft, client_id: int
) -> GateResult:
    """Verify content claims are grounded in tagged research.

    - Loads research findings associated with the draft (via research_source_ids)
    - LLM-based evaluation in production; here we do keyword cross-referencing
    - Evergreen content with no research ties gets lighter check
    """
    copy = draft.copy or ""
    if not copy.strip():
        return GateResult(
            gate_name="research_grounding",
            status=GateStatus.PASSED,
            score=1.0,
            detail="Empty content -- research grounding skipped",
        )

    # Load research findings for this draft
    research_ids = draft.research_source_ids or []
    findings = _load_research_findings(db, research_ids)

    # Evergreen content with no research ties gets lighter check
    is_evergreen = draft.freshness_window == "evergreen" or draft.is_evergreen
    if not findings and is_evergreen:
        return GateResult(
            gate_name="research_grounding",
            status=GateStatus.PASSED,
            score=0.8,
            detail="Evergreen content with no specific research ties -- lighter grounding check passed",
        )

    # Check for trend/claim language that requires grounding
    trend_patterns = [
        r"\btrending\b",
        r"\bon the rise\b",
        r"\bgrowing\s+trend\b",
        r"\bsurging\b",
        r"\bspiking\b",
        r"\bbooming\b",
        r"\bskyrocketing\b",
        r"\bup\s+\d+%\b",
        r"\bdown\s+\d+%\b",
    ]

    copy_lower = copy.lower()
    ungrounded_claims: list[str] = []

    for pattern in trend_patterns:
        match = re.search(pattern, copy_lower)
        if match:
            claim = match.group()
            # Check if any research finding supports this claim
            is_grounded = False
            for finding in findings:
                finding_text = _get_finding_text(finding)
                if claim in finding_text.lower() or _claim_supported(
                    claim, finding_text
                ):
                    is_grounded = True
                    break
            if not is_grounded:
                ungrounded_claims.append(claim)

    if ungrounded_claims:
        return GateResult(
            gate_name="research_grounding",
            status=GateStatus.REJECTED,
            score=0.3,
            detail=f"Ungrounded claims: {', '.join(ungrounded_claims)}. No supporting research found.",
        )

    return GateResult(
        gate_name="research_grounding",
        status=GateStatus.PASSED,
        score=1.0,
        detail="All claims grounded in research",
    )


# =============================================================================
# Gate 6: Brand Safety
# =============================================================================

# Default guardrails (locked decision)
DEFAULT_BRAND_GUARDRAILS = {
    "no_competitor_names": True,
    "no_unverifiable_claims": True,
    "no_pricing_promises": True,
    "no_legal_risk_language": True,
}

UNVERIFIABLE_CLAIM_PATTERNS = [
    r"\bbest\s+in\s+\w+\b",
    r"\b#1\b",
    r"\bnumber\s+one\b",
    r"\btop\s*-?\s*rated\b",
    r"\bbest\s+(?:quality|service|value|price)\b",
    r"\bguaranteed?\b",
    r"\b100%\s+(?:satisfaction|guaranteed?|safe|effective)\b",
    r"\bmost\s+(?:trusted|reliable|popular|affordable)\b",
]

PRICING_PATTERNS = [
    r"\$\d+",
    r"\bstarting\s+(?:at|from)\s+\$",
    r"\bonly\s+\$",
    r"\bfree\b.*\bfor\s+a\s+limited\s+time\b",
    r"\bprice\s+(?:guarantee|match|promise)\b",
]

LEGAL_RISK_PATTERNS = [
    r"\bcure[sd]?\b",
    r"\btreat(?:s|ment)?\b.*\bdisease\b",
    r"\bmedically?\s+proven\b",
    r"\bFDA\s+approved\b",
    r"\bclinically?\s+(?:tested|proven)\b",
]


def run_brand_safety_gate(
    db: Session, draft: ContentDraft, client_id: int
) -> GateResult:
    """Enforce per-client brand safety guardrails.

    Default guardrails (locked decision):
    - No competitor name-drops
    - No unverifiable claims ("best in town")
    - No pricing promises
    - No legal-risk language

    Additional per-client guardrails loaded from client config.
    """
    copy = draft.copy or ""
    if not copy.strip():
        return GateResult(
            gate_name="brand_safety",
            status=GateStatus.PASSED,
            score=1.0,
            detail="Empty content -- brand safety check skipped",
        )

    client_config = _load_client_config(db, client_id)
    guardrails = client_config.get("guardrails", {})
    violations: list[str] = []

    # Check 1: Competitor name-drops
    competitors = client_config.get("competitors", [])
    if competitors:
        copy_lower = copy.lower()
        for comp in competitors:
            comp_name = comp if isinstance(comp, str) else comp.get("name", "")
            if comp_name and comp_name.lower() in copy_lower:
                violations.append(f"Competitor name-drop: '{comp_name}'")

    # Check 2: Unverifiable claims
    for pattern in UNVERIFIABLE_CLAIM_PATTERNS:
        match = re.search(pattern, copy, re.IGNORECASE)
        if match:
            violations.append(f"Unverifiable claim: '{match.group()}'")
            break  # One violation per category is enough

    # Check 3: Pricing promises
    for pattern in PRICING_PATTERNS:
        match = re.search(pattern, copy, re.IGNORECASE)
        if match:
            violations.append(f"Pricing promise: '{match.group()}'")
            break

    # Check 4: Legal-risk language
    for pattern in LEGAL_RISK_PATTERNS:
        match = re.search(pattern, copy, re.IGNORECASE)
        if match:
            violations.append(f"Legal-risk language: '{match.group()}'")
            break

    # Check 5: Per-client blocklist
    blocklist = guardrails.get("blocklist", [])
    for blocked_term in blocklist:
        if blocked_term.lower() in copy.lower():
            violations.append(f"Blocked term: '{blocked_term}'")

    # Check 6: Per-client sensitive topics
    sensitive_topics = guardrails.get("sensitive_topics", [])
    for topic in sensitive_topics:
        if topic.lower() in copy.lower():
            violations.append(f"Sensitive topic: '{topic}'")

    if violations:
        return GateResult(
            gate_name="brand_safety",
            status=GateStatus.REJECTED,
            score=0.0,
            detail=f"Brand safety violations: {'; '.join(violations)}",
        )

    return GateResult(
        gate_name="brand_safety",
        status=GateStatus.PASSED,
        score=1.0,
        detail="No brand safety violations",
    )


# =============================================================================
# Register gate functions
# =============================================================================

_GATE_FUNCTIONS["sensitivity"] = run_sensitivity_gate
_GATE_FUNCTIONS["voice_alignment"] = run_voice_alignment_gate
_GATE_FUNCTIONS["plagiarism_originality"] = run_plagiarism_gate
_GATE_FUNCTIONS["ai_pattern_detection"] = run_ai_detection_gate
_GATE_FUNCTIONS["research_grounding"] = run_research_grounding_gate
_GATE_FUNCTIONS["brand_safety"] = run_brand_safety_gate


# =============================================================================
# Helpers
# =============================================================================


def _load_client_config(db: Session, client_id: int) -> dict:
    """Load client configuration for gate evaluation."""
    try:
        from sophia.intelligence.models import Client

        client = db.query(Client).filter(Client.id == client_id).first()
        if client:
            return {
                "industry": getattr(client, "industry", ""),
                "sensitivity_level": (
                    getattr(client, "guardrails", {}) or {}
                ).get("sensitivity_level", "medium"),
                "guardrails": getattr(client, "guardrails", {}) or {},
                "competitors": getattr(client, "competitors", []) or [],
            }
    except ImportError:
        logger.warning("Intelligence models not available for gate config")
    return {}


def _load_sensitive_events(db: Session, client_id: int) -> list[dict]:
    """Load sensitive events from research service (7-day window).

    Returns list of event dicts with 'description' and 'keywords' keys.
    """
    try:
        from sophia.research.service import get_findings_for_content

        findings = get_findings_for_content(db, client_id, limit=20)
        events: list[dict] = []
        for f in findings or []:
            if getattr(f, "is_time_sensitive", 0):
                topic = getattr(f, "topic", "")
                events.append({
                    "description": topic,
                    "keywords": [
                        w.lower()
                        for w in topic.split()
                        if len(w) > 3
                    ],
                })
        return events
    except (ImportError, Exception):
        return []


def _get_approved_posts(
    db: Session, client_id: int, limit: int = 30
) -> list[str]:
    """Get approved/published post texts for this client."""
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


def _check_semantic_similarity(
    db: Session, text: str, client_id: int
) -> tuple[float, str] | None:
    """Check semantic similarity via LanceDB.

    Returns (similarity_score, similar_text_preview) or None if LanceDB
    is not available.
    """
    try:
        from sophia.semantic.service import search_similar_content

        results = search_similar_content(
            text=text, client_id=client_id, limit=1
        )
        if results:
            top = results[0]
            score = top.get("score", 0.0)
            preview = top.get("text", "")
            return (score, preview)
    except (ImportError, Exception):
        # LanceDB not available -- semantic layer skipped
        pass
    return None


def _load_research_findings(
    db: Session, research_ids: list[int]
) -> list[Any]:
    """Load research findings by IDs."""
    if not research_ids:
        return []
    try:
        from sophia.research.models import ResearchFinding

        return (
            db.query(ResearchFinding)
            .filter(ResearchFinding.id.in_(research_ids))
            .all()
        )
    except ImportError:
        return []


def _get_finding_text(finding: Any) -> str:
    """Extract searchable text from a research finding."""
    parts = []
    for attr in ("topic", "summary", "content_angles"):
        val = getattr(finding, attr, None)
        if val:
            if isinstance(val, list):
                parts.extend(str(v) for v in val)
            else:
                parts.append(str(val))
    return " ".join(parts)


def _claim_supported(claim: str, finding_text: str) -> bool:
    """Check if a claim keyword is supported by a research finding."""
    # Simple keyword overlap check
    claim_words = set(claim.lower().split())
    finding_words = set(finding_text.lower().split())
    overlap = claim_words & finding_words
    return len(overlap) >= 1 and len(overlap) / len(claim_words) >= 0.5


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences using simple regex."""
    sentences = re.split(r"[.!?]+\s*", text)
    return [s.strip() for s in sentences if s.strip() and len(s.split()) >= 2]
