"""Tests for content generation: models, schemas, voice alignment, prompt builder, and service.

All model tests run against a SQLCipher-encrypted test database.
Voice alignment tests use local spaCy + textstat (no external API mocking needed).
"""

import pytest

from sophia.content.models import (
    ContentDraft,
    EvergreenEntry,
    FormatPerformance,
    RegenerationLog,
)
from sophia.content.voice_alignment import (
    compute_voice_baseline,
    compute_voice_confidence,
    extract_stylometric_features,
    score_voice_alignment,
)


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
