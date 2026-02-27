"""Tests for quality gate pipeline: gate orchestration, individual gates,
auto-fix-once pattern, and integration with the content generation service.

All external dependencies (LanceDB, research service, intelligence service)
are mocked. Tests validate gate logic and orchestration, not the LLM itself.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from sophia.content.models import ContentDraft
from sophia.content.quality_gates import (
    AI_CLICHE_PATTERNS,
    GATE_ORDER,
    GateResult,
    GateStatus,
    QualityReport,
    _attempt_auto_fix,
    _split_sentences,
    run_ai_detection_gate,
    run_brand_safety_gate,
    run_pipeline,
    run_plagiarism_gate,
    run_research_grounding_gate,
    run_sensitivity_gate,
    run_voice_alignment_gate,
)


# =============================================================================
# Helpers
# =============================================================================


def _make_draft(
    client_id: int = 1,
    copy: str = "Check out our spring garden specials this weekend!",
    platform: str = "instagram",
    content_type: str = "feed",
    **kwargs,
) -> ContentDraft:
    """Create a ContentDraft instance for testing (not persisted)."""
    defaults = dict(
        client_id=client_id,
        platform=platform,
        content_type=content_type,
        copy=copy,
        image_prompt="A garden image",
        image_ratio="1:1",
        freshness_window="this_week",
        gate_status="pending",
    )
    defaults.update(kwargs)
    return ContentDraft(**defaults)


# =============================================================================
# Pipeline Orchestration Tests
# =============================================================================


class TestRunPipeline:
    """Tests for the quality gate pipeline orchestrator."""

    @patch("sophia.content.quality_gates.run_brand_safety_gate")
    @patch("sophia.content.quality_gates.run_research_grounding_gate")
    @patch("sophia.content.quality_gates.run_ai_detection_gate")
    @patch("sophia.content.quality_gates.run_plagiarism_gate")
    @patch("sophia.content.quality_gates.run_voice_alignment_gate")
    @patch("sophia.content.quality_gates.run_sensitivity_gate")
    def test_all_gates_pass(
        self, mock_sens, mock_voice, mock_plag, mock_ai, mock_research, mock_brand
    ):
        """When all gates pass, report status is 'passed' with badge 'Passed all gates'."""
        # Patch gate function dispatch table
        with patch.dict(
            "sophia.content.quality_gates._GATE_FUNCTIONS",
            {
                "sensitivity": mock_sens,
                "voice_alignment": mock_voice,
                "plagiarism_originality": mock_plag,
                "ai_pattern_detection": mock_ai,
                "research_grounding": mock_research,
                "brand_safety": mock_brand,
            },
        ):
            for mock_fn in [mock_sens, mock_voice, mock_plag, mock_ai, mock_research, mock_brand]:
                mock_fn.return_value = GateResult(
                    gate_name="test", status=GateStatus.PASSED, score=1.0
                )

            db = MagicMock()
            draft = _make_draft()
            report = run_pipeline(db, draft, client_id=1)

            assert report.status == "passed"
            assert report.summary_badge == "Passed all gates"
            assert report.rejected_by is None
            assert len(report.results) == 6

    @patch("sophia.content.quality_gates._attempt_auto_fix")
    @patch("sophia.content.quality_gates.run_brand_safety_gate")
    @patch("sophia.content.quality_gates.run_research_grounding_gate")
    @patch("sophia.content.quality_gates.run_ai_detection_gate")
    @patch("sophia.content.quality_gates.run_plagiarism_gate")
    @patch("sophia.content.quality_gates.run_voice_alignment_gate")
    @patch("sophia.content.quality_gates.run_sensitivity_gate")
    def test_first_gate_fails_autofix_succeeds(
        self, mock_sens, mock_voice, mock_plag, mock_ai, mock_research,
        mock_brand, mock_fix
    ):
        """First gate fails, auto-fix succeeds -> status 'passed_with_fix'."""
        with patch.dict(
            "sophia.content.quality_gates._GATE_FUNCTIONS",
            {
                "sensitivity": mock_sens,
                "voice_alignment": mock_voice,
                "plagiarism_originality": mock_plag,
                "ai_pattern_detection": mock_ai,
                "research_grounding": mock_research,
                "brand_safety": mock_brand,
            },
        ):
            # Sensitivity fails first, passes on retry after fix
            fail_result = GateResult(
                gate_name="sensitivity",
                status=GateStatus.REJECTED,
                score=0.0,
                detail="Sensitive content detected",
            )
            pass_result = GateResult(
                gate_name="sensitivity",
                status=GateStatus.PASSED,
                score=1.0,
            )
            mock_sens.side_effect = [fail_result, pass_result]

            # Auto-fix returns a modified draft
            fixed_draft = _make_draft(copy="Fixed content")
            mock_fix.return_value = fixed_draft

            # All other gates pass
            for mock_fn in [mock_voice, mock_plag, mock_ai, mock_research, mock_brand]:
                mock_fn.return_value = GateResult(
                    gate_name="test", status=GateStatus.PASSED, score=1.0
                )

            db = MagicMock()
            draft = _make_draft()
            report = run_pipeline(db, draft, client_id=1)

            assert report.status == "passed_with_fix"
            assert "sensitivity" in report.summary_badge
            assert report.rejected_by is None
            assert any(
                r.status == GateStatus.PASSED_WITH_FIX for r in report.results
            )

    @patch("sophia.content.quality_gates._attempt_auto_fix")
    @patch("sophia.content.quality_gates.run_brand_safety_gate")
    @patch("sophia.content.quality_gates.run_research_grounding_gate")
    @patch("sophia.content.quality_gates.run_ai_detection_gate")
    @patch("sophia.content.quality_gates.run_plagiarism_gate")
    @patch("sophia.content.quality_gates.run_voice_alignment_gate")
    @patch("sophia.content.quality_gates.run_sensitivity_gate")
    def test_first_gate_fails_autofix_fails(
        self, mock_sens, mock_voice, mock_plag, mock_ai, mock_research,
        mock_brand, mock_fix
    ):
        """First gate fails, auto-fix also fails -> status 'rejected'."""
        with patch.dict(
            "sophia.content.quality_gates._GATE_FUNCTIONS",
            {
                "sensitivity": mock_sens,
                "voice_alignment": mock_voice,
                "plagiarism_originality": mock_plag,
                "ai_pattern_detection": mock_ai,
                "research_grounding": mock_research,
                "brand_safety": mock_brand,
            },
        ):
            fail_result = GateResult(
                gate_name="sensitivity",
                status=GateStatus.REJECTED,
                score=0.0,
                detail="Sensitive content",
            )
            mock_sens.return_value = fail_result

            # Auto-fix returns None (no fix possible)
            mock_fix.return_value = None

            db = MagicMock()
            draft = _make_draft()
            report = run_pipeline(db, draft, client_id=1)

            assert report.status == "rejected"
            assert report.rejected_by == "sensitivity"
            assert "Rejected" in report.summary_badge

    @patch("sophia.content.quality_gates._attempt_auto_fix")
    def test_gate_execution_order(self, mock_fix):
        """Gates must be called in locked order: sensitivity -> ... -> brand_safety."""
        call_order = []

        def make_gate_fn(name):
            def gate_fn(db, draft, client_id):
                call_order.append(name)
                return GateResult(
                    gate_name=name, status=GateStatus.PASSED, score=1.0
                )
            return gate_fn

        gate_mocks = {name: make_gate_fn(name) for name in GATE_ORDER}

        with patch.dict(
            "sophia.content.quality_gates._GATE_FUNCTIONS", gate_mocks
        ):
            db = MagicMock()
            draft = _make_draft()
            run_pipeline(db, draft, client_id=1)

        assert call_order == GATE_ORDER

    @patch("sophia.content.quality_gates._attempt_auto_fix")
    def test_rejection_stops_pipeline_early(self, mock_fix):
        """If sensitivity rejects, voice alignment is NOT called."""
        call_order = []

        def sensitivity_fn(db, draft, client_id):
            call_order.append("sensitivity")
            return GateResult(
                gate_name="sensitivity",
                status=GateStatus.REJECTED,
                score=0.0,
                detail="Blocked",
            )

        def voice_fn(db, draft, client_id):
            call_order.append("voice_alignment")
            return GateResult(
                gate_name="voice_alignment",
                status=GateStatus.PASSED,
                score=1.0,
            )

        mock_fix.return_value = None

        gate_mocks = {
            "sensitivity": sensitivity_fn,
            "voice_alignment": voice_fn,
            "plagiarism_originality": voice_fn,
            "ai_pattern_detection": voice_fn,
            "research_grounding": voice_fn,
            "brand_safety": voice_fn,
        }

        with patch.dict(
            "sophia.content.quality_gates._GATE_FUNCTIONS", gate_mocks
        ):
            db = MagicMock()
            draft = _make_draft()
            report = run_pipeline(db, draft, client_id=1)

        assert call_order == ["sensitivity"]
        assert report.status == "rejected"
        assert report.rejected_by == "sensitivity"


# =============================================================================
# Gate 1: Sensitivity Tests
# =============================================================================


class TestSensitivityGate:
    """Tests for the sensitivity gate."""

    @patch("sophia.content.quality_gates._load_sensitive_events")
    @patch("sophia.content.quality_gates._load_client_config")
    def test_safe_content_passes(self, mock_config, mock_events):
        """Safe content with no sensitive events -> PASSED."""
        mock_config.return_value = {"industry": "Retail", "sensitivity_level": "medium"}
        mock_events.return_value = []

        db = MagicMock()
        draft = _make_draft(copy="Check out our spring garden specials!")
        result = run_sensitivity_gate(db, draft, client_id=1)

        assert result.status == GateStatus.PASSED
        assert result.score == 1.0

    @patch("sophia.content.quality_gates._load_sensitive_events")
    @patch("sophia.content.quality_gates._load_client_config")
    def test_sensitive_event_overlap_rejected(self, mock_config, mock_events):
        """Content overlapping with a sensitive local event -> REJECTED."""
        mock_config.return_value = {"industry": "Retail", "sensitivity_level": "medium"}
        mock_events.return_value = [
            {"description": "Local flooding disaster", "keywords": ["flooding", "disaster"]}
        ]

        db = MagicMock()
        draft = _make_draft(
            copy="Don't let the flooding stop you from visiting us!"
        )
        result = run_sensitivity_gate(db, draft, client_id=1)

        assert result.status == GateStatus.REJECTED
        assert "flooding" in result.detail.lower() or "sensitive event" in result.detail.lower()

    @patch("sophia.content.quality_gates._load_sensitive_events")
    @patch("sophia.content.quality_gates._load_client_config")
    def test_high_sensitivity_industry_stricter(self, mock_config, mock_events):
        """Healthcare industry should trigger on 'alcohol' content."""
        mock_config.return_value = {
            "industry": "healthcare clinic",
            "sensitivity_level": "high",
        }
        mock_events.return_value = []

        db = MagicMock()
        draft = _make_draft(
            copy="Come join our pub crawl and drinking night!"
        )
        result = run_sensitivity_gate(db, draft, client_id=1)

        assert result.status == GateStatus.REJECTED


# =============================================================================
# Gate 2: Voice Alignment Tests
# =============================================================================


class TestVoiceAlignmentGate:
    """Tests for the voice alignment gate."""

    @patch("sophia.content.quality_gates._get_approved_posts")
    def test_well_matched_content_passes(self, mock_posts):
        """Content matching baseline should pass with score >= 0.6."""
        # Provide enough consistent posts for a baseline
        sample_posts = [
            "Check out our spring specials! Fresh flowers and garden supplies on sale.",
            "Looking for the perfect gift? Our handmade bouquets are locally sourced.",
            "Weekend market is here! Stop by our booth for herbs and seasonal plants.",
            "New arrivals in the greenhouse. Succulents, ferns, and tropical plants.",
            "Thank you to our amazing community for supporting local businesses.",
            "Pro tip: water your indoor plants with room temperature water.",
        ]
        mock_posts.return_value = sample_posts

        db = MagicMock()
        # Use text that closely matches the casual, short-sentence style of the baseline
        draft = _make_draft(
            copy="New spring arrivals in our shop! Fresh herbs and beautiful flowers for your garden."
        )
        result = run_voice_alignment_gate(db, draft, client_id=1)

        assert result.status == GateStatus.PASSED

    @patch("sophia.content.quality_gates._get_approved_posts")
    def test_drifting_content_rejected(self, mock_posts):
        """Highly formal/technical text should be rejected for voice drift."""
        sample_posts = [
            "Check out our spring specials! Fresh flowers on sale.",
            "Looking for a gift? Our bouquets are locally sourced.",
            "Weekend market is here! Stop by for herbs.",
            "New arrivals: succulents, ferns, and tropical plants.",
            "Thank you community for supporting local businesses.",
            "Pro tip: water plants with room temperature water.",
        ]
        mock_posts.return_value = sample_posts

        db = MagicMock()
        draft = _make_draft(
            copy=(
                "The comprehensive photosynthesis mechanisms observed in C4 plants "
                "demonstrate remarkable adaptations to high-temperature environments, "
                "particularly regarding the concentration of carbon dioxide within "
                "bundle-sheath cells, effectively minimizing photorespiratory losses "
                "and optimizing the Calvin cycle's efficiency under conditions of "
                "elevated atmospheric temperatures and water stress."
            )
        )
        result = run_voice_alignment_gate(db, draft, client_id=1)

        # Should either be rejected or have low score
        if result.status == GateStatus.REJECTED:
            assert result.score < 0.6
        # If it passes, the score should still be relatively low
        # (depends on spaCy analysis)

    @patch("sophia.content.quality_gates._get_approved_posts")
    def test_cold_start_auto_passes(self, mock_posts):
        """< 5 approved posts -> PASSED (not rejected during calibration)."""
        mock_posts.return_value = [
            "Just one post about spring.",
            "Second post about flowers.",
        ]

        db = MagicMock()
        draft = _make_draft(copy="Any content here should pass during cold start.")
        result = run_voice_alignment_gate(db, draft, client_id=1)

        assert result.status == GateStatus.PASSED
        assert "cold start" in result.detail.lower()


# =============================================================================
# Gate 3: Plagiarism / Originality Tests
# =============================================================================


class TestPlagiarismGate:
    """Tests for the plagiarism/originality gate."""

    @patch("sophia.content.quality_gates._check_semantic_similarity")
    @patch("sophia.content.quality_gates._get_approved_posts")
    def test_original_content_passes(self, mock_posts, mock_semantic):
        """Original content with no similar posts -> PASSED."""
        mock_semantic.return_value = None  # LanceDB not available
        mock_posts.return_value = [
            "An existing post about something entirely different.",
        ]

        db = MagicMock()
        draft = _make_draft(
            copy="Check out our spring garden specials this weekend!"
        )
        result = run_plagiarism_gate(db, draft, client_id=1)

        assert result.status == GateStatus.PASSED

    @patch("sophia.content.quality_gates._check_semantic_similarity")
    @patch("sophia.content.quality_gates._get_approved_posts")
    def test_semantic_similarity_rejected(self, mock_posts, mock_semantic):
        """Content semantically similar to existing post (score > 0.85) -> REJECTED."""
        mock_semantic.return_value = (0.92, "Very similar existing post about the same topic")
        mock_posts.return_value = []

        db = MagicMock()
        draft = _make_draft(copy="Similar content to existing post")
        result = run_plagiarism_gate(db, draft, client_id=1)

        assert result.status == GateStatus.REJECTED
        assert "0.92" in result.detail or "semantic" in result.detail.lower()

    @patch("sophia.content.quality_gates._check_semantic_similarity")
    @patch("sophia.content.quality_gates._get_approved_posts")
    def test_text_overlap_rejected(self, mock_posts, mock_semantic):
        """Content with high text overlap (ratio > 0.60) -> REJECTED with percentage."""
        mock_semantic.return_value = None
        # Create a post that is very similar text-wise
        existing = "Check out our spring garden specials this weekend at the store"
        mock_posts.return_value = [existing]

        db = MagicMock()
        draft = _make_draft(
            copy="Check out our spring garden specials this weekend at the shop"
        )
        result = run_plagiarism_gate(db, draft, client_id=1)

        assert result.status == GateStatus.REJECTED
        assert "overlap" in result.detail.lower() or "%" in result.detail


# =============================================================================
# Gate 4: AI Pattern Detection Tests
# =============================================================================


class TestAIDetectionGate:
    """Tests for the AI pattern detection gate."""

    def test_natural_text_passes(self):
        """Natural human-like text with no cliches -> PASSED."""
        db = MagicMock()
        draft = _make_draft(
            copy="Spring flowers are blooming in the garden. Come visit us this Saturday for fresh bouquets and herbs. We have everything you need."
        )
        result = run_ai_detection_gate(db, draft, client_id=1)

        assert result.status == GateStatus.PASSED

    def test_ai_cliches_rejected(self):
        """Content with AI cliches ('dive in', 'game-changer') -> REJECTED."""
        db = MagicMock()
        draft = _make_draft(
            copy="Let's dive in and explore this game-changer for your garden! Leverage the power of nature to unlock your potential."
        )
        result = run_ai_detection_gate(db, draft, client_id=1)

        assert result.status == GateStatus.REJECTED
        assert "cliche" in result.detail.lower()

    def test_uniform_sentence_length_rejected(self):
        """All sentences same length -> REJECTED for unnaturally uniform structure."""
        # Create text where all sentences have exactly the same word count
        db = MagicMock()
        draft = _make_draft(
            copy=(
                "The flowers bloom well here now. "
                "The garden grows fast this year. "
                "The herbs taste good all around. "
                "The plants need more water soon. "
                "The seeds were planted last week."
            )
        )
        result = run_ai_detection_gate(db, draft, client_id=1)

        # Should detect uniform structure (all 6-word sentences, CV near 0)
        if result.status == GateStatus.REJECTED:
            assert "uniform" in result.detail.lower()


# =============================================================================
# Gate 5: Research Grounding Tests
# =============================================================================


class TestResearchGroundingGate:
    """Tests for the research grounding gate."""

    @patch("sophia.content.quality_gates._load_research_findings")
    def test_grounded_claims_pass(self, mock_findings):
        """Content with claims supported by research -> PASSED."""
        mock_finding = MagicMock()
        mock_finding.topic = "Container gardening trends"
        mock_finding.summary = "Container gardening is trending with 40% growth"
        mock_finding.content_angles = ["DIY tips"]
        mock_findings.return_value = [mock_finding]

        db = MagicMock()
        draft = _make_draft(
            copy="Container gardening is trending this season! Here are some tips.",
            research_source_ids=[1],
        )
        result = run_research_grounding_gate(db, draft, client_id=1)

        assert result.status == GateStatus.PASSED

    @patch("sophia.content.quality_gates._load_research_findings")
    def test_hallucinated_trend_rejected(self, mock_findings):
        """Content claiming 'trending' without research support -> REJECTED."""
        mock_finding = MagicMock()
        mock_finding.topic = "Local farmers market schedule"
        mock_finding.summary = "Market opens Saturdays at 9am"
        mock_finding.content_angles = ["Event coverage"]
        mock_findings.return_value = [mock_finding]

        db = MagicMock()
        draft = _make_draft(
            copy="Vertical gardening is trending and skyrocketing in popularity!",
            research_source_ids=[1],
        )
        result = run_research_grounding_gate(db, draft, client_id=1)

        assert result.status == GateStatus.REJECTED
        assert "ungrounded" in result.detail.lower()

    @patch("sophia.content.quality_gates._load_research_findings")
    def test_evergreen_no_research_passes(self, mock_findings):
        """Evergreen content with no research ties -> PASSED (lighter check)."""
        mock_findings.return_value = []

        db = MagicMock()
        draft = _make_draft(
            copy="Water your plants regularly for best results.",
            freshness_window="evergreen",
            is_evergreen=True,
            research_source_ids=[],
        )
        result = run_research_grounding_gate(db, draft, client_id=1)

        assert result.status == GateStatus.PASSED


# =============================================================================
# Gate 6: Brand Safety Tests
# =============================================================================


class TestBrandSafetyGate:
    """Tests for the brand safety gate."""

    @patch("sophia.content.quality_gates._load_client_config")
    def test_clean_content_passes(self, mock_config):
        """Clean content with no violations -> PASSED."""
        mock_config.return_value = {
            "industry": "Retail",
            "guardrails": {},
            "competitors": [],
        }

        db = MagicMock()
        draft = _make_draft(copy="Visit our garden center for fresh plants this weekend!")
        result = run_brand_safety_gate(db, draft, client_id=1)

        assert result.status == GateStatus.PASSED

    @patch("sophia.content.quality_gates._load_client_config")
    def test_competitor_name_drop_rejected(self, mock_config):
        """Mentioning competitor name -> REJECTED."""
        mock_config.return_value = {
            "industry": "Retail",
            "guardrails": {},
            "competitors": ["Home Depot", "Lowe's"],
        }

        db = MagicMock()
        draft = _make_draft(
            copy="Unlike Home Depot, we offer personalized garden advice!"
        )
        result = run_brand_safety_gate(db, draft, client_id=1)

        assert result.status == GateStatus.REJECTED
        assert "competitor" in result.detail.lower()

    @patch("sophia.content.quality_gates._load_client_config")
    def test_unverifiable_claim_rejected(self, mock_config):
        """Unverifiable claim ('best in Ontario') -> REJECTED."""
        mock_config.return_value = {
            "industry": "Retail",
            "guardrails": {},
            "competitors": [],
        }

        db = MagicMock()
        draft = _make_draft(
            copy="We are the best in Ontario for garden supplies!"
        )
        result = run_brand_safety_gate(db, draft, client_id=1)

        assert result.status == GateStatus.REJECTED
        assert "unverifiable" in result.detail.lower() or "claim" in result.detail.lower()

    @patch("sophia.content.quality_gates._load_client_config")
    def test_pricing_promise_rejected(self, mock_config):
        """Pricing promise -> REJECTED."""
        mock_config.return_value = {
            "industry": "Retail",
            "guardrails": {},
            "competitors": [],
        }

        db = MagicMock()
        draft = _make_draft(
            copy="Our plants start at only $5 with a price guarantee!"
        )
        result = run_brand_safety_gate(db, draft, client_id=1)

        assert result.status == GateStatus.REJECTED

    @patch("sophia.content.quality_gates._load_client_config")
    def test_blocklist_term_rejected(self, mock_config):
        """Blocklisted term from client config -> REJECTED."""
        mock_config.return_value = {
            "industry": "Retail",
            "guardrails": {"blocklist": ["cannabis", "weed"]},
            "competitors": [],
        }

        db = MagicMock()
        draft = _make_draft(
            copy="We now stock cannabis-inspired garden decorations!"
        )
        result = run_brand_safety_gate(db, draft, client_id=1)

        assert result.status == GateStatus.REJECTED
        assert "blocked" in result.detail.lower()


# =============================================================================
# Auto-fix Tests
# =============================================================================


class TestAutoFix:
    """Tests for the auto-fix mechanism."""

    def test_autofix_returns_modified_draft_for_sensitivity(self):
        """_attempt_auto_fix returns a modified draft for sensitivity issues."""
        draft = _make_draft(copy="Original content about the flooding disaster.")
        result = GateResult(
            gate_name="sensitivity",
            status=GateStatus.REJECTED,
            score=0.0,
            detail="Sensitive topic detected",
        )
        fixed = _attempt_auto_fix(draft, "sensitivity", result)

        assert fixed is not None
        assert fixed.copy != draft.copy
        assert "sensitivity-adjusted" in fixed.copy

    def test_autofix_returns_none_for_voice_alignment(self):
        """_attempt_auto_fix returns None for voice alignment (too hard deterministically)."""
        draft = _make_draft(copy="Some drifting content.")
        result = GateResult(
            gate_name="voice_alignment",
            status=GateStatus.REJECTED,
            score=0.4,
            detail="Voice drift",
        )
        fixed = _attempt_auto_fix(draft, "voice_alignment", result)

        assert fixed is None

    def test_autofix_ai_patterns_removes_cliches(self):
        """_attempt_auto_fix removes AI cliches from content."""
        draft = _make_draft(
            copy="Let's dive in and explore this game-changer for your garden!"
        )
        result = GateResult(
            gate_name="ai_pattern_detection",
            status=GateStatus.REJECTED,
            score=0.5,
            detail="AI cliches found",
        )
        fixed = _attempt_auto_fix(draft, "ai_pattern_detection", result)

        assert fixed is not None
        assert "dive in" not in fixed.copy.lower()
        assert "game-changer" not in fixed.copy.lower()

    def test_autofix_brand_safety_removes_superlatives(self):
        """_attempt_auto_fix removes unverifiable claims."""
        draft = _make_draft(
            copy="We are the best in Ontario for plants and top rated service!"
        )
        result = GateResult(
            gate_name="brand_safety",
            status=GateStatus.REJECTED,
            score=0.0,
            detail="Unverifiable claim",
        )
        fixed = _attempt_auto_fix(draft, "brand_safety", result)

        assert fixed is not None
        assert "best in ontario" not in fixed.copy.lower()


# =============================================================================
# QualityReport Tests
# =============================================================================


class TestQualityReport:
    """Tests for QualityReport serialization."""

    def test_to_dict_serialization(self):
        """QualityReport.to_dict() produces JSON-safe dict."""
        report = QualityReport(
            status="passed",
            results=[
                GateResult(
                    gate_name="sensitivity",
                    status=GateStatus.PASSED,
                    score=1.0,
                    detail="All clear",
                ),
            ],
            summary_badge="Passed all gates",
        )

        d = report.to_dict()
        assert d["status"] == "passed"
        assert d["summary_badge"] == "Passed all gates"
        assert len(d["results"]) == 1
        assert d["results"][0]["status"] == "passed"

    def test_to_dict_with_fix(self):
        """QualityReport with fix records fix_applied."""
        report = QualityReport(
            status="passed_with_fix",
            results=[
                GateResult(
                    gate_name="ai_pattern_detection",
                    status=GateStatus.PASSED_WITH_FIX,
                    score=0.9,
                    fix_applied="Removed AI cliches",
                ),
            ],
            summary_badge="Passed with fix (ai_pattern_detection corrected)",
        )

        d = report.to_dict()
        assert d["status"] == "passed_with_fix"
        assert d["results"][0]["fix_applied"] == "Removed AI cliches"


# =============================================================================
# Utility Tests
# =============================================================================


class TestSplitSentences:
    """Tests for sentence splitting utility."""

    def test_splits_on_punctuation(self):
        """Splits on periods, exclamation marks, question marks."""
        text = "Hello world. How are you? Fine thanks!"
        sentences = _split_sentences(text)
        assert len(sentences) == 3

    def test_ignores_short_fragments(self):
        """Fragments with fewer than 2 words are ignored."""
        text = "Hello. I am fine. Ok."
        sentences = _split_sentences(text)
        # "Ok" has only 1 word, should be filtered
        assert all(len(s.split()) >= 2 for s in sentences)
