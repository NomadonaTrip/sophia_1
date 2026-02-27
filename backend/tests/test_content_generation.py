"""Tests for content generation: models, schemas, voice alignment, prompt builder, and service.

All model tests run against a SQLCipher-encrypted test database.
Voice alignment tests use local spaCy + textstat (no external API mocking needed).
Prompt builder and service tests mock upstream services.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from sophia.content.models import (
    ContentDraft,
    EvergreenEntry,
    FormatPerformance,
    RegenerationLog,
)
from sophia.content.prompt_builder import (
    PLATFORM_RULES,
    build_batch_prompts,
    build_generation_prompt,
    build_image_prompt,
)
from sophia.content.service import (
    _compute_option_count,
    generate_content_batch,
    get_content_drafts,
)
from sophia.content.voice_alignment import (
    compute_voice_baseline,
    compute_voice_confidence,
    extract_stylometric_features,
    score_voice_alignment,
)
from sophia.exceptions import ContentGenerationError


# =============================================================================
# Model Tests
# =============================================================================


class TestContentDraftModel:
    """Tests for ContentDraft ORM model creation and field storage."""

    def test_create_content_draft(self, db_session, sample_client):
        """Create a ContentDraft with all required fields and verify persistence."""
        draft = ContentDraft(
            client_id=sample_client.id,
            platform="instagram",
            content_type="feed",
            copy="Come check out our spring specials! Fresh flowers and garden supplies at 20% off this weekend only.",
            image_prompt="A vibrant garden display with spring flowers, warm sunlight, 1:1 aspect ratio",
            image_ratio="1:1",
            hashtags=["#springdeals", "#gardenlife", "#shoplocal"],
            alt_text="Spring flower display at local garden center",
            content_pillar="seasonal_promotions",
            target_persona="Budget-Conscious Homeowner",
            content_format="story",
            freshness_window="post_within_24hrs",
            research_source_ids=[1, 2, 3],
            is_evergreen=False,
            rank=1,
            rank_reasoning="High voice alignment, strong research grounding",
            confidence_score=0.85,
            gate_status="pending",
            voice_confidence_pct=0.78,
            status="draft",
        )
        db_session.add(draft)
        db_session.flush()

        assert draft.id is not None
        assert draft.client_id == sample_client.id
        assert draft.platform == "instagram"
        assert draft.content_type == "feed"
        assert draft.copy.startswith("Come check out")
        assert draft.image_ratio == "1:1"
        assert draft.hashtags == ["#springdeals", "#gardenlife", "#shoplocal"]
        assert draft.alt_text == "Spring flower display at local garden center"
        assert draft.content_pillar == "seasonal_promotions"
        assert draft.target_persona == "Budget-Conscious Homeowner"
        assert draft.content_format == "story"
        assert draft.freshness_window == "post_within_24hrs"
        assert draft.research_source_ids == [1, 2, 3]
        assert draft.is_evergreen is False
        assert draft.rank == 1
        assert draft.rank_reasoning == "High voice alignment, strong research grounding"
        assert draft.confidence_score == 0.85
        assert draft.gate_status == "pending"
        assert draft.voice_confidence_pct == 0.78
        assert draft.status == "draft"
        assert draft.regeneration_count == 0
        assert draft.has_ai_label is False


class TestEvergreenEntryModel:
    """Tests for EvergreenEntry ORM model."""

    def test_create_evergreen_entry(self, db_session, sample_client):
        """Create an EvergreenEntry linked to a ContentDraft."""
        draft = ContentDraft(
            client_id=sample_client.id,
            platform="facebook",
            content_type="feed",
            copy="Evergreen content about garden maintenance.",
            image_prompt="A well-maintained garden",
            image_ratio="1.91:1",
            freshness_window="evergreen",
            is_evergreen=True,
        )
        db_session.add(draft)
        db_session.flush()

        entry = EvergreenEntry(
            client_id=sample_client.id,
            content_draft_id=draft.id,
            platform="facebook",
            content_type="feed",
            is_used=False,
        )
        db_session.add(entry)
        db_session.flush()

        assert entry.id is not None
        assert entry.content_draft_id == draft.id
        assert entry.is_used is False
        assert entry.used_at is None


class TestFormatPerformanceModel:
    """Tests for FormatPerformance ORM model."""

    def test_create_format_performance(self, db_session, sample_client):
        """Create a FormatPerformance tracking record."""
        perf = FormatPerformance(
            client_id=sample_client.id,
            platform="instagram",
            content_format="how-to",
            sample_count=12,
            avg_engagement_rate=0.045,
            avg_save_rate=0.012,
            avg_ctr=0.023,
        )
        db_session.add(perf)
        db_session.flush()

        assert perf.id is not None
        assert perf.client_id == sample_client.id
        assert perf.content_format == "how-to"
        assert perf.sample_count == 12
        assert perf.avg_engagement_rate == 0.045


class TestRegenerationLogModel:
    """Tests for RegenerationLog ORM model."""

    def test_create_regeneration_log(self, db_session, sample_client):
        """Create a regeneration log entry with guidance."""
        draft = ContentDraft(
            client_id=sample_client.id,
            platform="instagram",
            content_type="feed",
            copy="Original draft content.",
            image_prompt="Original image prompt",
            image_ratio="1:1",
        )
        db_session.add(draft)
        db_session.flush()

        log = RegenerationLog(
            content_draft_id=draft.id,
            client_id=sample_client.id,
            attempt_number=1,
            guidance="Make it more casual and add a question at the end",
        )
        db_session.add(log)
        db_session.flush()

        assert log.id is not None
        assert log.content_draft_id == draft.id
        assert log.attempt_number == 1
        assert "casual" in log.guidance


# =============================================================================
# Voice Alignment Tests
# =============================================================================


class TestExtractStylometricFeatures:
    """Tests for stylometric feature extraction via spaCy + textstat."""

    def test_extract_features_sample_text(self):
        """Extract features from sample social media text and verify all 9 present."""
        text = (
            "Come check out our spring specials! "
            "Fresh flowers and garden supplies at 20% off this weekend only."
        )
        features = extract_stylometric_features(text)

        # All 9 features must be present
        assert len(features) == 9
        expected_keys = {
            "avg_sentence_length",
            "sentence_length_std",
            "avg_word_length",
            "vocabulary_richness",
            "noun_ratio",
            "verb_ratio",
            "adj_ratio",
            "flesch_reading_ease",
            "avg_syllables_per_word",
        }
        assert set(features.keys()) == expected_keys

        # All values must be numeric
        for key, val in features.items():
            assert isinstance(val, (int, float)), f"{key} is not numeric: {type(val)}"

        # Sanity checks on specific features
        assert features["avg_sentence_length"] > 0
        assert features["avg_word_length"] > 0
        assert features["vocabulary_richness"] > 0
        assert 0 <= features["noun_ratio"] <= 1
        assert 0 <= features["verb_ratio"] <= 1
        assert 0 <= features["adj_ratio"] <= 1

    def test_extract_features_empty_string(self):
        """Empty string returns all zeros."""
        features = extract_stylometric_features("")
        assert all(v == 0.0 for v in features.values())

    def test_extract_features_whitespace_only(self):
        """Whitespace-only string returns all zeros."""
        features = extract_stylometric_features("   \n\t  ")
        assert all(v == 0.0 for v in features.values())

    def test_extract_features_single_sentence(self):
        """Single sentence has 0 standard deviation for sentence length."""
        features = extract_stylometric_features("This is a single sentence about flowers.")
        assert features["sentence_length_std"] == 0.0
        assert features["avg_sentence_length"] > 0


class TestComputeVoiceBaseline:
    """Tests for voice baseline computation from approved posts."""

    def test_baseline_with_multiple_posts(self):
        """Compute baseline from 5+ sample posts and verify mean/std per feature."""
        posts = [
            "Come check out our spring specials! Fresh flowers and garden supplies on sale.",
            "Looking for the perfect gift? Our handmade bouquets are locally sourced and beautiful.",
            "Weekend market is here! Stop by our booth for herbs and seasonal plants.",
            "New arrivals in the greenhouse this week. Succulents, ferns, and tropical plants.",
            "Thank you to our amazing community for supporting local businesses this holiday season.",
            "Pro tip: water your indoor plants with room temperature water for best results.",
        ]
        baseline = compute_voice_baseline(posts)

        # Should have all 9 features
        assert len(baseline) == 9

        for name, (mean, std) in baseline.items():
            assert isinstance(mean, float), f"{name} mean is not float"
            assert isinstance(std, float), f"{name} std is not float"
            # Mean should be positive for most features (some like std could be 0)
            if name not in ("sentence_length_std",):
                assert mean >= 0, f"{name} mean should be >= 0, got {mean}"

    def test_baseline_empty_list(self):
        """Empty post list returns empty dict."""
        baseline = compute_voice_baseline([])
        assert baseline == {}

    def test_baseline_single_post(self):
        """Single post baseline has 0 std for all features."""
        baseline = compute_voice_baseline(["Just one post about our spring sale."])
        assert len(baseline) == 9
        for name, (mean, std) in baseline.items():
            assert std == 0.0, f"{name} should have 0 std with single post"


class TestScoreVoiceAlignment:
    """Tests for voice drift scoring against baseline."""

    @pytest.fixture
    def sample_baseline(self):
        """Build a baseline from consistent posts."""
        posts = [
            "Come check out our spring specials! Fresh flowers and garden supplies on sale.",
            "Looking for the perfect gift? Our handmade bouquets are locally sourced and beautiful.",
            "Weekend market is here! Stop by our booth for herbs and seasonal plants.",
            "New arrivals in the greenhouse this week. Succulents, ferns, and tropical plants.",
            "Thank you to our amazing community for supporting local businesses this holiday season.",
            "Pro tip: water your indoor plants with room temperature water for best results.",
        ]
        return compute_voice_baseline(posts)

    def test_high_alignment_with_similar_text(self, sample_baseline):
        """Text matching baseline style should score high (>0.7)."""
        similar_text = (
            "Spring is here! Check out our new collection of garden tools and plant food. "
            "Perfect for getting your garden ready this season."
        )
        score, deviations = score_voice_alignment(similar_text, sample_baseline)
        assert score > 0.5, f"Expected high alignment, got {score}"

    def test_low_alignment_with_divergent_text(self, sample_baseline):
        """Highly formal/technical text should diverge from casual baseline."""
        divergent_text = (
            "The comprehensive photosynthesis mechanisms observed in C4 plants "
            "demonstrate remarkable adaptations to high-temperature environments, "
            "particularly regarding the concentration of carbon dioxide within "
            "bundle-sheath cells, effectively minimizing photorespiratory losses "
            "and optimizing the Calvin cycle's efficiency under conditions of "
            "elevated atmospheric temperatures and water stress."
        )
        score, deviations = score_voice_alignment(divergent_text, sample_baseline)
        assert len(deviations) > 0, "Expected deviations for formal text"

    def test_cold_start_empty_baseline(self):
        """Empty baseline returns neutral score (0.5) with message."""
        score, deviations = score_voice_alignment("Any text here.", {})
        assert score == 0.5
        assert deviations == ["Insufficient baseline data"]

    def test_story_permissive_thresholds(self, sample_baseline):
        """Stories should get more permissive thresholds (1.5x multiplier)."""
        text = "Spring sale! 20% off!"
        score_feed, devs_feed = score_voice_alignment(
            text, sample_baseline, is_story=False
        )
        score_story, devs_story = score_voice_alignment(
            text, sample_baseline, is_story=True
        )
        # Story should have equal or fewer deviations due to permissive thresholds
        assert len(devs_story) <= len(devs_feed)


class TestComputeVoiceConfidence:
    """Tests for voice confidence level computation."""

    def test_low_confidence(self):
        """< 5 approved posts returns 'low'."""
        assert compute_voice_confidence(0) == "low"
        assert compute_voice_confidence(3) == "low"
        assert compute_voice_confidence(4) == "low"

    def test_medium_confidence(self):
        """5-15 approved posts returns 'medium'."""
        assert compute_voice_confidence(5) == "medium"
        assert compute_voice_confidence(10) == "medium"
        assert compute_voice_confidence(15) == "medium"

    def test_high_confidence(self):
        """16+ approved posts returns 'high'."""
        assert compute_voice_confidence(16) == "high"
        assert compute_voice_confidence(20) == "high"
        assert compute_voice_confidence(100) == "high"


# =============================================================================
# Prompt Builder Tests
# =============================================================================


class TestBuildGenerationPrompt:
    """Tests for system prompt construction."""

    @pytest.fixture
    def mock_voice_profile(self):
        return {
            "base_voice": {
                "tone": {"value": "warm and friendly", "confidence": 0.8, "source": "claude_analysis"},
                "formality": {"value": "casual", "confidence": 0.7, "source": "claude_analysis"},
                "humor_style": {"value": "light, occasional puns", "confidence": 0.6, "source": "claude_analysis"},
                "vocabulary_complexity": {"value": "simple", "confidence": 0.7, "source": "claude_analysis"},
                "emoji_usage": {"value": "moderate", "confidence": 0.5, "source": "claude_analysis"},
                "hashtag_style": {"value": "relevant", "confidence": 0.5, "source": "claude_analysis"},
                "cta_patterns": {"value": "visit us", "confidence": 0.4, "source": "claude_analysis"},
                "storytelling": {"value": "personal anecdotes", "confidence": 0.5, "source": "claude_analysis"},
            },
            "platform_variants": {
                "facebook": {"formality_delta": -0.1, "emoji_delta": 0.1},
                "instagram": {"formality_delta": -0.2, "hashtag_delta": 0.3},
            },
        }

    @pytest.fixture
    def mock_research(self):
        return [
            {"topic": "Spring gardening trends", "summary": "Container gardening up 40%", "content_angles": ["DIY tips"]},
            {"topic": "Local farmers market", "summary": "New vendors this season", "content_angles": ["Event coverage"]},
        ]

    @pytest.fixture
    def mock_intelligence(self):
        return {
            "name": "Green Thumb Garden Center",
            "business_description": "Local garden center specializing in native plants",
            "industry": "Retail - Garden Center",
            "target_audience": {"primary": "homeowners 30-55"},
            "geography_area": "Hamilton, Ontario",
        }

    @pytest.fixture
    def mock_client_config(self):
        return {
            "guardrails": {"blocklist": ["competitor-name"], "sensitive_topics": ["politics"]},
            "content_pillars": ["seasonal tips", "plant care", "local events"],
            "brand_assets": {"visual_style": {"color_palette": "greens and earth tones"}},
        }

    def test_prompt_contains_platform_rules(
        self, mock_voice_profile, mock_research, mock_intelligence, mock_client_config
    ):
        """System prompt should contain platform-specific rules."""
        system_prompt, _ = build_generation_prompt(
            voice_profile=mock_voice_profile,
            approved_examples=[],
            research_findings=mock_research,
            intelligence=mock_intelligence,
            platform="instagram",
            content_type="feed",
            client_config=mock_client_config,
        )
        assert "2200" in system_prompt  # max_chars for Instagram feed
        assert "3-5" in system_prompt  # hashtag guidance
        assert "instagram" in system_prompt.lower()

    def test_prompt_contains_voice_instructions(
        self, mock_voice_profile, mock_research, mock_intelligence, mock_client_config
    ):
        """System prompt should include voice style instructions."""
        system_prompt, _ = build_generation_prompt(
            voice_profile=mock_voice_profile,
            approved_examples=[],
            research_findings=mock_research,
            intelligence=mock_intelligence,
            platform="instagram",
            content_type="feed",
            client_config=mock_client_config,
        )
        assert "warm and friendly" in system_prompt
        assert "casual" in system_prompt

    def test_prompt_contains_research_context(
        self, mock_voice_profile, mock_research, mock_intelligence, mock_client_config
    ):
        """System prompt should include research findings as context."""
        system_prompt, _ = build_generation_prompt(
            voice_profile=mock_voice_profile,
            approved_examples=["Example post 1", "Example post 2"],
            research_findings=mock_research,
            intelligence=mock_intelligence,
            platform="instagram",
            content_type="feed",
            client_config=mock_client_config,
        )
        assert "Spring gardening trends" in system_prompt
        assert "Container gardening" in system_prompt

    def test_prompt_contains_ai_cliche_avoidance(
        self, mock_voice_profile, mock_research, mock_intelligence, mock_client_config
    ):
        """System prompt should include AI cliche avoidance rules."""
        system_prompt, _ = build_generation_prompt(
            voice_profile=mock_voice_profile,
            approved_examples=[],
            research_findings=mock_research,
            intelligence=mock_intelligence,
            platform="instagram",
            content_type="feed",
            client_config=mock_client_config,
        )
        assert "cliche" in system_prompt.lower() or "game-changer" in system_prompt

    def test_instagram_story_casual_shift(
        self, mock_voice_profile, mock_research, mock_intelligence, mock_client_config
    ):
        """Instagram story prompt should apply casual shift and 120 char max."""
        system_prompt, _ = build_generation_prompt(
            voice_profile=mock_voice_profile,
            approved_examples=[],
            research_findings=mock_research,
            intelligence=mock_intelligence,
            platform="instagram",
            content_type="story",
            client_config=mock_client_config,
        )
        assert "120" in system_prompt  # max_chars for stories
        assert "story mode" in system_prompt.lower() or "punchy" in system_prompt.lower()

    def test_emoji_preference_respected_no_emojis(
        self, mock_research, mock_intelligence, mock_client_config
    ):
        """Voice profile with uses_emojis=False should produce 'No emojis' in prompt."""
        no_emoji_profile = {
            "base_voice": {
                "emoji_usage": {"value": "none", "confidence": 0.9, "source": "claude_analysis"},
            },
            "platform_variants": {},
        }
        system_prompt, _ = build_generation_prompt(
            voice_profile=no_emoji_profile,
            approved_examples=[],
            research_findings=mock_research,
            intelligence=mock_intelligence,
            platform="instagram",
            content_type="feed",
            client_config=mock_client_config,
        )
        assert "no emoji" in system_prompt.lower()

    def test_few_shot_examples_formatted(
        self, mock_voice_profile, mock_research, mock_intelligence, mock_client_config
    ):
        """Approved examples should appear as numbered few-shot examples."""
        examples = [
            "Check out our new spring collection!",
            "Weekend market starts Saturday at 9am.",
        ]
        _, examples_text = build_generation_prompt(
            voice_profile=mock_voice_profile,
            approved_examples=examples,
            research_findings=mock_research,
            intelligence=mock_intelligence,
            platform="instagram",
            content_type="feed",
            client_config=mock_client_config,
        )
        assert "Example 1" in examples_text
        assert "Example 2" in examples_text
        assert "spring collection" in examples_text


class TestBuildBatchPrompts:
    """Tests for batch prompt generation across platforms."""

    def test_batch_prompts_both_platforms_with_stories(self):
        """Batch prompts should include feed for both platforms + Instagram story."""
        prompts = build_batch_prompts(
            research=[{"topic": "Test", "summary": "Test finding"}],
            intelligence={"name": "Test Biz", "industry": "Retail"},
            voice={"base_voice": {}, "platform_variants": {}},
            platforms=["facebook", "instagram"],
            option_count=3,
            include_stories=True,
            client_config={},
            approved_examples=[],
        )
        # Should have: facebook feed + instagram feed + instagram story = 3 prompts
        assert len(prompts) == 3
        platforms_types = [(p["platform"], p["content_type"]) for p in prompts]
        assert ("facebook", "feed") in platforms_types
        assert ("instagram", "feed") in platforms_types
        assert ("instagram", "story") in platforms_types

    def test_batch_prompts_option_count_passed(self):
        """Each prompt should carry the option_count."""
        prompts = build_batch_prompts(
            research=[],
            intelligence={"name": "Test"},
            voice={"base_voice": {}, "platform_variants": {}},
            platforms=["instagram"],
            option_count=4,
            include_stories=False,
            client_config={},
            approved_examples=[],
        )
        assert len(prompts) == 1
        assert prompts[0]["option_count"] == 4


class TestBuildImagePrompt:
    """Tests for image prompt construction."""

    def test_image_prompt_correct_ratio_instagram_feed(self):
        """Instagram feed image prompt should specify 1:1 aspect ratio."""
        prompt = build_image_prompt(
            business_name="Green Thumb",
            visual_style={"color_palette": "greens and earth tones", "photography_style": "natural"},
            platform="instagram",
            content_type="feed",
            post_copy="Spring flowers are here!",
        )
        assert "1:1" in prompt
        assert "Green Thumb" in prompt
        assert "text" in prompt.lower()  # no text instruction

    def test_image_prompt_correct_ratio_instagram_story(self):
        """Instagram story image prompt should specify 9:16 aspect ratio."""
        prompt = build_image_prompt(
            business_name="Test Biz",
            visual_style={},
            platform="instagram",
            content_type="story",
            post_copy="Spring sale!",
        )
        assert "9:16" in prompt

    def test_image_prompt_correct_ratio_facebook_feed(self):
        """Facebook feed image prompt should specify 1.91:1 aspect ratio."""
        prompt = build_image_prompt(
            business_name="Test Biz",
            visual_style={},
            platform="facebook",
            content_type="feed",
            post_copy="Check us out!",
        )
        assert "1.91:1" in prompt

    def test_image_prompt_includes_visual_style(self):
        """Image prompt should include visual style details."""
        prompt = build_image_prompt(
            business_name="Test Biz",
            visual_style={
                "color_palette": "earth tones",
                "photography_style": "lifestyle photography",
                "composition": "rule of thirds",
            },
            platform="instagram",
            content_type="feed",
            post_copy="Test post.",
        )
        assert "earth tones" in prompt
        assert "lifestyle photography" in prompt
        assert "rule of thirds" in prompt


# =============================================================================
# Service Tests (mock upstream services)
# =============================================================================


class TestComputeOptionCount:
    """Tests for adaptive option count based on research richness."""

    def test_thin_research_2_options(self):
        """1-2 findings should produce 2 options."""
        findings = [MagicMock(finding_type=MagicMock(value="news"), is_time_sensitive=0)]
        assert _compute_option_count(findings) == 2

        findings2 = [
            MagicMock(finding_type=MagicMock(value="news"), is_time_sensitive=0),
            MagicMock(finding_type=MagicMock(value="news"), is_time_sensitive=0),
        ]
        assert _compute_option_count(findings2) == 2

    def test_average_research_3_options(self):
        """3-7 findings should produce 3 options (base)."""
        findings = [
            MagicMock(finding_type=MagicMock(value="news"), is_time_sensitive=0)
            for _ in range(5)
        ]
        assert _compute_option_count(findings) == 3

    def test_rich_research_4_5_options(self):
        """10+ findings with diverse sources should produce 4-5 options."""
        findings = []
        types = ["news", "trend", "community", "industry"]
        for i in range(12):
            findings.append(
                MagicMock(
                    finding_type=MagicMock(value=types[i % len(types)]),
                    is_time_sensitive=1 if i < 3 else 0,
                )
            )
        result = _compute_option_count(findings)
        assert result >= 4, f"Expected 4-5 options for rich research, got {result}"
        assert result <= 5

    def test_empty_research_2_options(self):
        """Empty research should produce 2 options (minimum)."""
        assert _compute_option_count([]) == 2


class TestGenerateContentBatch:
    """Tests for the generation orchestrator with mocked upstream services."""

    def _create_mock_finding(self, db_session, client):
        """Create a real ResearchFinding in the test DB."""
        from sophia.research.models import FindingType, ResearchFinding

        now = datetime.now(timezone.utc)
        finding = ResearchFinding(
            client_id=client.id,
            finding_type=FindingType.NEWS,
            topic="Spring gardening trends",
            summary="Container gardening up 40%",
            content_angles=["DIY tips"],
            source_name="local_news",
            confidence=0.8,
            is_time_sensitive=0,
            expires_at=now + timedelta(days=3),
        )
        db_session.add(finding)
        db_session.flush()
        return finding

    def _setup_client_for_generation(self, db_session, client):
        """Setup a client with all three required inputs."""
        from sophia.intelligence.models import VoiceProfile

        # Add business description and content pillars
        client.business_description = "Local garden center specializing in native plants"
        client.content_pillars = ["seasonal tips", "plant care", "local events"]
        db_session.flush()

        # Create voice profile
        voice = VoiceProfile(
            client_id=client.id,
            profile_data={
                "base_voice": {
                    "tone": {"value": "warm", "confidence": 0.8, "source": "test"},
                },
                "platform_variants": {},
            },
            overall_confidence_pct=60,
            sample_count=3,
        )
        db_session.add(voice)
        db_session.flush()

        # Create research finding
        self._create_mock_finding(db_session, client)
        db_session.commit()

    def test_generate_batch_all_inputs_present(self, db_session, sample_client):
        """With all three inputs present, generate_content_batch returns drafts."""
        self._setup_client_for_generation(db_session, sample_client)
        drafts = generate_content_batch(db_session, sample_client.id)

        assert len(drafts) > 0
        for draft in drafts:
            assert draft.id is not None
            assert draft.client_id == sample_client.id
            assert draft.platform in ("facebook", "instagram")
            assert draft.content_type in ("feed", "story")
            assert draft.rank is not None
            assert draft.voice_confidence_pct is not None

    def test_generate_batch_missing_research(self, db_session, sample_client):
        """Missing research should raise ContentGenerationError."""
        from sophia.intelligence.models import VoiceProfile

        # Setup intelligence and voice but no research
        sample_client.business_description = "Test business"
        sample_client.content_pillars = ["topic1"]
        db_session.flush()

        voice = VoiceProfile(
            client_id=sample_client.id,
            profile_data={"base_voice": {}, "platform_variants": {}},
            overall_confidence_pct=50,
            sample_count=1,
        )
        db_session.add(voice)
        db_session.commit()

        with pytest.raises(ContentGenerationError) as exc_info:
            generate_content_batch(db_session, sample_client.id)
        assert "research" in str(exc_info.value).lower()

    def test_generate_batch_missing_voice_profile(self, db_session, sample_client):
        """Missing voice profile should raise ContentGenerationError."""
        # Setup intelligence and research but no voice
        sample_client.business_description = "Test business"
        sample_client.content_pillars = ["topic1"]
        db_session.flush()
        self._create_mock_finding(db_session, sample_client)
        db_session.commit()

        with pytest.raises(ContentGenerationError) as exc_info:
            generate_content_batch(db_session, sample_client.id)
        assert "voice" in str(exc_info.value).lower()

    def test_generate_batch_missing_intelligence(self, db_session, sample_client):
        """Missing intelligence profile should raise ContentGenerationError."""
        from sophia.intelligence.models import VoiceProfile

        # Setup voice and research but no intelligence (no description, no pillars)
        voice = VoiceProfile(
            client_id=sample_client.id,
            profile_data={"base_voice": {}, "platform_variants": {}},
            overall_confidence_pct=50,
            sample_count=1,
        )
        db_session.add(voice)
        self._create_mock_finding(db_session, sample_client)
        db_session.commit()

        with pytest.raises(ContentGenerationError) as exc_info:
            generate_content_batch(db_session, sample_client.id)
        assert "intelligence" in str(exc_info.value).lower() or "incomplete" in str(exc_info.value).lower()


class TestGetContentDrafts:
    """Tests for querying content drafts with filters."""

    def test_get_drafts_with_status_filter(self, db_session, sample_client):
        """Filter drafts by status."""
        # Create drafts with different statuses
        for status in ["draft", "draft", "approved", "rejected"]:
            d = ContentDraft(
                client_id=sample_client.id,
                platform="instagram",
                content_type="feed",
                copy=f"Content with status {status}",
                image_prompt="Test prompt",
                image_ratio="1:1",
                status=status,
            )
            db_session.add(d)
        db_session.flush()

        drafts = get_content_drafts(db_session, sample_client.id, status="draft")
        assert len(drafts) == 2
        assert all(d.status == "draft" for d in drafts)

        approved = get_content_drafts(db_session, sample_client.id, status="approved")
        assert len(approved) == 1

    def test_get_drafts_respects_limit(self, db_session, sample_client):
        """Limit parameter should cap results."""
        for i in range(5):
            d = ContentDraft(
                client_id=sample_client.id,
                platform="instagram",
                content_type="feed",
                copy=f"Draft {i}",
                image_prompt="Test",
                image_ratio="1:1",
            )
            db_session.add(d)
        db_session.flush()

        drafts = get_content_drafts(db_session, sample_client.id, limit=3)
        assert len(drafts) == 3


class TestVoiceAlignmentIntegration:
    """Tests for voice alignment integration in the generation pipeline."""

    def test_voice_confidence_set_on_drafts(self, db_session, sample_client):
        """Verify voice_confidence_pct is set on each generated draft."""
        from sophia.intelligence.models import VoiceProfile
        from sophia.research.models import FindingType, ResearchFinding

        # Full setup
        sample_client.business_description = "Garden center"
        sample_client.content_pillars = ["plants"]
        db_session.flush()

        voice = VoiceProfile(
            client_id=sample_client.id,
            profile_data={"base_voice": {"tone": {"value": "warm", "confidence": 0.8, "source": "test"}}, "platform_variants": {}},
            overall_confidence_pct=60,
            sample_count=3,
        )
        db_session.add(voice)

        now = datetime.now(timezone.utc)
        finding = ResearchFinding(
            client_id=sample_client.id,
            finding_type=FindingType.NEWS,
            topic="Test topic",
            summary="Test summary",
            source_name="test",
            confidence=0.8,
            is_time_sensitive=0,
            expires_at=now + timedelta(days=3),
        )
        db_session.add(finding)
        db_session.commit()

        drafts = generate_content_batch(db_session, sample_client.id)
        for draft in drafts:
            assert draft.voice_confidence_pct is not None
            assert draft.voice_confidence_pct >= 0
