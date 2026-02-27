"""Tests for VoiceService: extraction pipeline, confidence scoring, material management.

Uses conftest.py fixtures: test_engine, db_session, sample_client.
"""

import pytest

from sophia.intelligence.models import AuditLog, VoiceMaterial, VoiceProfile
from sophia.intelligence.schemas import VoiceMaterialCreate
from sophia.intelligence.voice import VoiceService
from sophia.exceptions import ValidationError, VoiceExtractionError


# ---------------------------------------------------------------------------
# Quantitative Analysis
# ---------------------------------------------------------------------------


class TestQuantitativeMetrics:
    """Tests for compute_quantitative_metrics (textstat-powered)."""

    def test_compute_quantitative_metrics_basic(self):
        """Multi-sentence text produces expected metrics with confidence 0.95."""
        text = (
            "The quick brown fox jumps over the lazy dog. "
            "She sells seashells by the seashore. "
            "How much wood would a woodchuck chuck?"
        )
        metrics = VoiceService.compute_quantitative_metrics(text)

        # Should have all 10 metric keys
        expected_keys = {
            "flesch_reading_ease",
            "avg_sentence_length",
            "syllable_count_per_word",
            "lexicon_count",
            "sentence_count",
            "avg_word_length",
            "exclamation_density",
            "question_density",
            "emoji_count",
            "hashtag_count",
        }
        assert set(metrics.keys()) == expected_keys

        # All should have confidence 0.95 and source "computed"
        for key, val in metrics.items():
            assert val["confidence"] == 0.95, f"{key} confidence != 0.95"
            assert val["source"] == "computed", f"{key} source != 'computed'"

        # Sentence count should be 3
        assert metrics["sentence_count"]["value"] == 3

        # Flesch reading ease should be a reasonable number
        assert isinstance(metrics["flesch_reading_ease"]["value"], (int, float))

        # Avg sentence length should be positive
        assert metrics["avg_sentence_length"]["value"] > 0

    def test_compute_quantitative_metrics_empty(self):
        """Empty string returns zero/default metrics without crashing."""
        metrics = VoiceService.compute_quantitative_metrics("")
        assert len(metrics) == 10
        assert metrics["lexicon_count"]["value"] == 0
        assert metrics["sentence_count"]["value"] == 0
        assert metrics["emoji_count"]["value"] == 0
        assert metrics["hashtag_count"]["value"] == 0
        assert metrics["avg_word_length"]["value"] == 0.0

    def test_compute_quantitative_metrics_whitespace_only(self):
        """Whitespace-only string returns zero/default metrics."""
        metrics = VoiceService.compute_quantitative_metrics("   \n\t  ")
        assert metrics["lexicon_count"]["value"] == 0
        assert metrics["sentence_count"]["value"] == 0

    def test_compute_quantitative_metrics_with_emojis(self):
        """Text with emojis has correct emoji_count."""
        text = "Great day at the park! \U0001F600\U0001F389\U0001F31E Having fun!"
        metrics = VoiceService.compute_quantitative_metrics(text)
        assert metrics["emoji_count"]["value"] >= 3

    def test_compute_quantitative_metrics_with_hashtags(self):
        """Text with #hashtags has correct hashtag_count."""
        text = "Loving this #sunny day! #Toronto #LifeIsGood"
        metrics = VoiceService.compute_quantitative_metrics(text)
        assert metrics["hashtag_count"]["value"] == 3

    def test_compute_quantitative_metrics_punctuation_density(self):
        """Exclamation and question density calculated correctly."""
        # Use clearly separated sentences for reliable textstat counting
        text = "This is amazing. Wow that is incredible! How are you doing? We love it!"
        metrics = VoiceService.compute_quantitative_metrics(text)
        sent_count = metrics["sentence_count"]["value"]
        # 2 exclamation marks, 1 question mark
        assert sent_count >= 2
        assert metrics["exclamation_density"]["value"] > 0
        assert metrics["question_density"]["value"] > 0


# ---------------------------------------------------------------------------
# Material Management
# ---------------------------------------------------------------------------


class TestMaterialManagement:
    """Tests for add_material and get_materials."""

    def test_add_material(self, db_session, sample_client):
        """Add a social_post material, verify stored with correct fields."""
        data = VoiceMaterialCreate(
            client_id=sample_client.id,
            source_type="social_post",
            content="Just had a great meeting with a new client! #business",
        )
        material = VoiceService.add_material(db_session, data)

        assert material.id is not None
        assert material.client_id == sample_client.id
        assert material.source_type == "social_post"
        assert "#business" in material.content

        # Verify audit log was created
        audit = (
            db_session.query(AuditLog)
            .filter(
                AuditLog.client_id == sample_client.id,
                AuditLog.action == "voice.material_added",
            )
            .first()
        )
        assert audit is not None
        assert audit.actor == "operator"

    def test_add_multiple_materials(self, db_session, sample_client):
        """Add social_post + website_copy, verify both stored, ordered by created_at."""
        data1 = VoiceMaterialCreate(
            client_id=sample_client.id,
            source_type="social_post",
            content="Morning post about our services.",
        )
        data2 = VoiceMaterialCreate(
            client_id=sample_client.id,
            source_type="website_copy",
            content="We provide premium marketing solutions for local businesses.",
        )
        VoiceService.add_material(db_session, data1)
        VoiceService.add_material(db_session, data2)

        materials = VoiceService.get_materials(db_session, sample_client.id)
        assert len(materials) == 2
        assert materials[0].source_type == "social_post"
        assert materials[1].source_type == "website_copy"

    def test_add_material_invalid_source_type(self, db_session, sample_client):
        """Invalid source_type raises ValidationError."""
        data = VoiceMaterialCreate.__new__(VoiceMaterialCreate)
        # Bypass pydantic validation to test service-level validation
        object.__setattr__(data, "client_id", sample_client.id)
        object.__setattr__(data, "source_type", "blog_post")
        object.__setattr__(data, "content", "Some content")
        object.__setattr__(data, "source_url", None)
        object.__setattr__(data, "metadata_", None)

        with pytest.raises(ValidationError, match="Invalid source_type"):
            VoiceService.add_material(db_session, data)


# ---------------------------------------------------------------------------
# Profile Construction
# ---------------------------------------------------------------------------


class TestProfileConstruction:
    """Tests for build_voice_profile."""

    def _add_material(self, db_session, client_id, text, source_type="social_post"):
        """Helper to add a voice material."""
        data = VoiceMaterialCreate(
            client_id=client_id,
            source_type=source_type,
            content=text,
        )
        return VoiceService.add_material(db_session, data)

    def test_build_voice_profile_single_material(self, db_session, sample_client):
        """Single material produces profile with quantitative metrics, qualitative defaults."""
        self._add_material(
            db_session,
            sample_client.id,
            "We are a passionate marketing team serving Southern Ontario businesses. "
            "Our approach combines creativity with data-driven strategy. "
            "Let us help you grow your brand today!",
        )

        profile = VoiceService.build_voice_profile(db_session, sample_client.id)

        # Structure checks
        assert "base_voice" in profile
        assert "platform_variants" in profile
        assert "overall_confidence" in profile
        assert "last_updated" in profile
        assert "sample_count" in profile
        assert profile["sample_count"] == 1

        # Quantitative metrics should be populated
        base = profile["base_voice"]
        assert base["flesch_reading_ease"]["confidence"] == 0.95
        assert base["avg_sentence_length"]["value"] > 0

        # Qualitative dimensions should be defaults (null/0.0)
        assert base["tone"]["value"] is None
        assert base["tone"]["confidence"] == 0.0
        assert base["formality"]["value"] is None

    def test_build_voice_profile_multiple_materials(self, db_session, sample_client):
        """Multiple materials produce aggregated quantitative metrics."""
        self._add_material(
            db_session,
            sample_client.id,
            "Morning energy! Ready to create amazing content for our clients.",
        )
        self._add_material(
            db_session,
            sample_client.id,
            "Our professional approach ensures every campaign delivers measurable results.",
            source_type="website_copy",
        )
        self._add_material(
            db_session,
            sample_client.id,
            "We believe in authentic storytelling that connects brands with their community.",
            source_type="website_copy",
        )

        profile = VoiceService.build_voice_profile(db_session, sample_client.id)
        assert profile["sample_count"] == 3

        # Quantitative metrics should be computed across all materials
        base = profile["base_voice"]
        assert base["sentence_count"]["value"] >= 3
        assert base["lexicon_count"]["value"] > 10

    def test_build_profile_includes_platform_variants(self, db_session, sample_client):
        """Built profile includes facebook and instagram platform variants."""
        self._add_material(
            db_session,
            sample_client.id,
            "Check out our latest work for local businesses!",
        )

        profile = VoiceService.build_voice_profile(db_session, sample_client.id)

        variants = profile["platform_variants"]
        assert "facebook" in variants
        assert "instagram" in variants
        assert "formality_delta" in variants["facebook"]
        assert "emoji_delta" in variants["facebook"]
        assert variants["facebook"]["formality_delta"] == -0.1
        assert variants["instagram"]["formality_delta"] == -0.2
        assert variants["instagram"]["hashtag_delta"] == 0.3

    def test_overall_confidence_with_only_quantitative(self, db_session, sample_client):
        """Profile with only computed metrics has low overall confidence (weight 0.3)."""
        self._add_material(
            db_session,
            sample_client.id,
            "We provide excellent marketing services. Our team is dedicated to results.",
        )

        profile = VoiceService.build_voice_profile(db_session, sample_client.id)

        # Only quantitative metrics have confidence (0.95 * 0.3 weight = ~0.285)
        # Qualitative dimensions are all at 0.0 confidence
        assert profile["overall_confidence"] <= 0.30
        assert profile["overall_confidence"] > 0

    def test_build_profile_no_materials_raises(self, db_session, sample_client):
        """Building profile with no materials raises VoiceExtractionError."""
        with pytest.raises(VoiceExtractionError, match="No voice materials"):
            VoiceService.build_voice_profile(db_session, sample_client.id)


# ---------------------------------------------------------------------------
# Qualitative Updates
# ---------------------------------------------------------------------------


class TestQualitativeUpdates:
    """Tests for update_qualitative_dimensions."""

    def _setup_profile(self, db_session, client):
        """Helper: add material, build profile, save it."""
        data = VoiceMaterialCreate(
            client_id=client.id,
            source_type="social_post",
            content="We create amazing content for local businesses. "
            "Our work is professional and results-driven. "
            "Contact us today for a consultation!",
        )
        VoiceService.add_material(db_session, data)
        profile_data = VoiceService.build_voice_profile(db_session, client.id)
        VoiceService.save_voice_profile(db_session, client.id, profile_data)
        return profile_data

    def test_update_qualitative_dimensions(self, db_session, sample_client):
        """Update tone and formality, verify merged correctly, quantitative preserved."""
        self._setup_profile(db_session, sample_client)

        dimensions = {
            "tone": {"value": "warm-professional", "confidence": 0.72},
            "formality": {"value": 0.65, "confidence": 0.80},
        }
        result = VoiceService.update_qualitative_dimensions(
            db_session, sample_client.id, dimensions
        )

        # Check the updated profile
        base = result.profile_data["base_voice"]
        assert base["tone"]["value"] == "warm-professional"
        assert base["tone"]["confidence"] == 0.72
        assert base["formality"]["value"] == 0.65
        assert base["formality"]["confidence"] == 0.80

        # Quantitative metrics should still be present
        assert base["flesch_reading_ease"]["confidence"] == 0.95
        assert base["avg_sentence_length"]["value"] > 0

    def test_update_qualitative_increases_confidence(self, db_session, sample_client):
        """After qualitative update, overall confidence should increase."""
        self._setup_profile(db_session, sample_client)

        # Get initial confidence
        initial = (
            db_session.query(VoiceProfile)
            .filter(VoiceProfile.client_id == sample_client.id)
            .first()
        )
        initial_confidence = initial.overall_confidence_pct

        # Update qualitative dimensions
        dimensions = {
            "tone": {"value": "warm-professional", "confidence": 0.72},
            "formality": {"value": 0.65, "confidence": 0.80},
            "humor_style": {"value": "subtle-witty", "confidence": 0.50},
        }
        VoiceService.update_qualitative_dimensions(
            db_session, sample_client.id, dimensions
        )

        # Refresh and check
        updated = (
            db_session.query(VoiceProfile)
            .filter(VoiceProfile.client_id == sample_client.id)
            .first()
        )
        assert updated.overall_confidence_pct > initial_confidence

    def test_update_qualitative_without_profile_raises(self, db_session, sample_client):
        """Updating qualitative dimensions without a profile raises error."""
        with pytest.raises(VoiceExtractionError, match="No voice profile exists"):
            VoiceService.update_qualitative_dimensions(
                db_session, sample_client.id, {"tone": {"value": "warm"}}
            )


# ---------------------------------------------------------------------------
# Save and Retrieve
# ---------------------------------------------------------------------------


class TestSaveAndRetrieve:
    """Tests for save_voice_profile."""

    def test_save_voice_profile(self, db_session, sample_client):
        """Save profile creates VoiceProfile row with correct fields."""
        data = VoiceMaterialCreate(
            client_id=sample_client.id,
            source_type="social_post",
            content="We love working with local businesses!",
        )
        VoiceService.add_material(db_session, data)
        profile_data = VoiceService.build_voice_profile(db_session, sample_client.id)

        result = VoiceService.save_voice_profile(
            db_session, sample_client.id, profile_data
        )

        assert result.id is not None
        assert result.client_id == sample_client.id
        assert result.overall_confidence_pct == int(
            profile_data["overall_confidence"] * 100
        )
        assert result.sample_count == 1
        assert result.last_calibrated_at is not None

    def test_save_updates_existing(self, db_session, sample_client):
        """Saving twice updates the same row (unique constraint on client_id)."""
        data = VoiceMaterialCreate(
            client_id=sample_client.id,
            source_type="social_post",
            content="First material for testing updates.",
        )
        VoiceService.add_material(db_session, data)
        profile_data = VoiceService.build_voice_profile(db_session, sample_client.id)

        first = VoiceService.save_voice_profile(
            db_session, sample_client.id, profile_data
        )
        first_id = first.id

        # Add another material and rebuild
        data2 = VoiceMaterialCreate(
            client_id=sample_client.id,
            source_type="website_copy",
            content="Professional marketing solutions for Southern Ontario businesses.",
        )
        VoiceService.add_material(db_session, data2)
        profile_data2 = VoiceService.build_voice_profile(db_session, sample_client.id)

        second = VoiceService.save_voice_profile(
            db_session, sample_client.id, profile_data2
        )

        # Same row updated, not duplicated
        assert second.id == first_id
        assert second.sample_count == 2

    def test_save_triggers_completeness_update(self, db_session, sample_client):
        """After saving voice profile, client's profile_completeness_pct should increase."""
        initial_pct = sample_client.profile_completeness_pct

        data = VoiceMaterialCreate(
            client_id=sample_client.id,
            source_type="social_post",
            content="Testing profile completeness update integration.",
        )
        VoiceService.add_material(db_session, data)
        profile_data = VoiceService.build_voice_profile(db_session, sample_client.id)
        VoiceService.save_voice_profile(db_session, sample_client.id, profile_data)

        # Refresh the client
        db_session.refresh(sample_client)
        assert sample_client.profile_completeness_pct >= initial_pct

    def test_save_creates_audit_log(self, db_session, sample_client):
        """Saving creates audit log with voice.extracted action."""
        data = VoiceMaterialCreate(
            client_id=sample_client.id,
            source_type="social_post",
            content="Audit log test content.",
        )
        VoiceService.add_material(db_session, data)
        profile_data = VoiceService.build_voice_profile(db_session, sample_client.id)
        VoiceService.save_voice_profile(db_session, sample_client.id, profile_data)

        audit = (
            db_session.query(AuditLog)
            .filter(
                AuditLog.client_id == sample_client.id,
                AuditLog.action == "voice.extracted",
            )
            .first()
        )
        assert audit is not None
        assert audit.after_snapshot is not None


# ---------------------------------------------------------------------------
# Confidence Explanation
# ---------------------------------------------------------------------------


class TestConfidenceExplanation:
    """Tests for explain_confidence."""

    def test_explain_confidence_ranges(self):
        """Test all five confidence ranges return appropriate strings."""
        # 0-20%
        msg = VoiceService.explain_confidence(10)
        assert "very little" in msg.lower()

        msg = VoiceService.explain_confidence(0)
        assert "very little" in msg.lower()

        msg = VoiceService.explain_confidence(20)
        assert "very little" in msg.lower()

        # 21-40%
        msg = VoiceService.explain_confidence(30)
        assert "rough sense" in msg.lower()

        msg = VoiceService.explain_confidence(40)
        assert "rough sense" in msg.lower()

        # 41-60%
        msg = VoiceService.explain_confidence(50)
        assert "working understanding" in msg.lower()

        # 61-80%
        msg = VoiceService.explain_confidence(70)
        assert "solid grasp" in msg.lower()

        # 81-100%
        msg = VoiceService.explain_confidence(90)
        assert "highly confident" in msg.lower()

        msg = VoiceService.explain_confidence(100)
        assert "highly confident" in msg.lower()


# ---------------------------------------------------------------------------
# No-Content Fallback
# ---------------------------------------------------------------------------


class TestFallbackProfile:
    """Tests for create_fallback_profile."""

    def test_create_fallback_profile_no_description(self, db_session, sample_client):
        """Fallback with just industry has low confidence (~10.5%)."""
        profile = VoiceService.create_fallback_profile(
            db_session, sample_client.id, industry="Marketing Agency"
        )

        assert profile["overall_confidence"] <= 0.15
        assert profile["sample_count"] == 0

        # Qualitative dimensions should have industry defaults
        base = profile["base_voice"]
        assert base["tone"]["value"] == "Marketing Agency-default"
        assert base["tone"]["confidence"] == 0.15
        assert base["tone"]["source"] == "industry_default"

        # Quantitative should be zeroed
        assert base["flesch_reading_ease"]["value"] == 0.0
        assert base["flesch_reading_ease"]["confidence"] == 0.0

    def test_create_fallback_profile_with_description(self, db_session, sample_client):
        """Fallback with operator description has slightly higher confidence (~17.5%)."""
        profile = VoiceService.create_fallback_profile(
            db_session,
            sample_client.id,
            industry="Marketing Agency",
            operator_description="We are a friendly, approachable team that uses casual language with clients.",
        )

        assert profile["overall_confidence"] > 0.15  # Higher than no-description
        assert profile["sample_count"] == 1

        # Material should be stored
        materials = VoiceService.get_materials(db_session, sample_client.id)
        assert len(materials) >= 1
        assert any(m.source_type == "operator_description" for m in materials)

        # Qualitative confidence should be 0.25 (higher than 0.15)
        base = profile["base_voice"]
        assert base["tone"]["confidence"] == 0.25


# ---------------------------------------------------------------------------
# Qualitative Defaults
# ---------------------------------------------------------------------------


class TestQualitativeDefaults:
    """Tests for get_qualitative_defaults."""

    def test_qualitative_defaults_structure(self):
        """Defaults have all 8 dimensions with null/0.0 values."""
        defaults = VoiceService.get_qualitative_defaults()

        expected_dims = {
            "tone", "formality", "vocabulary_complexity", "humor_style",
            "emoji_usage", "hashtag_style", "cta_patterns", "storytelling",
        }
        assert set(defaults.keys()) == expected_dims

        for dim_name, dim_data in defaults.items():
            assert dim_data["value"] is None, f"{dim_name} value should be None"
            assert dim_data["confidence"] == 0.0, f"{dim_name} confidence should be 0.0"
            assert dim_data["source"] is None, f"{dim_name} source should be None"
