"""Voice profile extraction and management service.

Provides infrastructure for:
- Storing raw voice materials (social posts, website copy, operator descriptions)
- Computing quantitative text metrics via textstat
- Building structured voice profiles with confidence scoring per dimension
- Managing qualitative dimension updates from Claude's runtime analysis
- No-content fallback profiles for new clients

The actual qualitative analysis (reading materials and determining tone, humor, etc.)
is NOT done by this service -- that's Claude's job at runtime. This service provides
the data pipeline: storing materials, computing quantitative metrics, maintaining the
profile structure, and managing confidence scores.
"""

import re
from datetime import datetime, timezone
from typing import Optional

import textstat
from sqlalchemy.orm import Session

from sophia.exceptions import ValidationError, VoiceExtractionError
from sophia.intelligence.models import AuditLog, Client, VoiceMaterial, VoiceProfile
from sophia.intelligence.schemas import VoiceMaterialCreate

# Valid source types for voice materials
VALID_SOURCE_TYPES = frozenset(
    {"social_post", "website_copy", "operator_description", "reference_account"}
)

# Qualitative voice dimensions (Claude fills these at runtime)
QUALITATIVE_DIMENSIONS = (
    "tone",
    "formality",
    "vocabulary_complexity",
    "humor_style",
    "emoji_usage",
    "hashtag_style",
    "cta_patterns",
    "storytelling",
)

# Confidence weights for overall calculation
QUANTITATIVE_WEIGHT = 0.3
QUALITATIVE_WEIGHT = 0.7

# Emoji regex: covers common emoji ranges (emoticons, symbols, dingbats, etc.)
_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # Emoticons
    "\U0001F300-\U0001F5FF"  # Misc Symbols and Pictographs
    "\U0001F680-\U0001F6FF"  # Transport and Map Symbols
    "\U0001F1E0-\U0001F1FF"  # Flags
    "\U00002702-\U000027B0"  # Dingbats
    "\U0001F900-\U0001F9FF"  # Supplemental Symbols
    "\U0001FA00-\U0001FA6F"  # Chess Symbols
    "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
    "\U00002600-\U000026FF"  # Misc Symbols
    "\U0000FE00-\U0000FE0F"  # Variation Selectors
    "\U0000200D"  # Zero Width Joiner
    "\U00002B50"  # Star
    "\U00002764"  # Heart
    "]+",
    flags=re.UNICODE,
)

# Hashtag pattern: # followed by word characters
_HASHTAG_PATTERN = re.compile(r"#\w+")


class VoiceService:
    """Voice profile extraction, scoring, material processing, and profile management."""

    # -------------------------------------------------------------------------
    # Material Management
    # -------------------------------------------------------------------------

    @staticmethod
    def add_material(db: Session, data: VoiceMaterialCreate) -> VoiceMaterial:
        """Store a raw voice material for a client.

        Validates source_type, persists the material, and creates an audit log entry.
        """
        if data.source_type not in VALID_SOURCE_TYPES:
            raise ValidationError(
                message=f"Invalid source_type: {data.source_type}",
                detail=f"Must be one of: {', '.join(sorted(VALID_SOURCE_TYPES))}",
                suggestion="Use social_post, website_copy, operator_description, or reference_account",
            )

        material = VoiceMaterial(
            client_id=data.client_id,
            source_type=data.source_type,
            content=data.content,
            source_url=data.source_url,
            metadata_=data.metadata_,
        )
        db.add(material)
        db.flush()

        audit = AuditLog(
            client_id=data.client_id,
            action="voice.material_added",
            actor="operator",
            details={
                "source_type": data.source_type,
                "content_length": len(data.content),
                "material_id": material.id,
            },
        )
        db.add(audit)
        db.commit()

        return material

    @staticmethod
    def get_materials(db: Session, client_id: int) -> list[VoiceMaterial]:
        """Return all voice materials for a client, ordered by created_at."""
        return (
            db.query(VoiceMaterial)
            .filter(VoiceMaterial.client_id == client_id)
            .order_by(VoiceMaterial.created_at)
            .all()
        )

    # -------------------------------------------------------------------------
    # Quantitative Analysis (textstat-powered)
    # -------------------------------------------------------------------------

    @staticmethod
    def compute_quantitative_metrics(text: str) -> dict:
        """Compute quantitative text metrics using textstat and standard Python.

        All computed values receive confidence=0.95 and source="computed".
        Returns dict of metric_name -> {value, confidence, source}.
        """
        confidence = 0.95
        source = "computed"

        # Handle empty/whitespace text gracefully
        if not text or not text.strip():
            return {
                "flesch_reading_ease": {"value": 0.0, "confidence": confidence, "source": source},
                "avg_sentence_length": {"value": 0.0, "confidence": confidence, "source": source},
                "syllable_count_per_word": {"value": 0.0, "confidence": confidence, "source": source},
                "lexicon_count": {"value": 0, "confidence": confidence, "source": source},
                "sentence_count": {"value": 0, "confidence": confidence, "source": source},
                "avg_word_length": {"value": 0.0, "confidence": confidence, "source": source},
                "exclamation_density": {"value": 0.0, "confidence": confidence, "source": source},
                "question_density": {"value": 0.0, "confidence": confidence, "source": source},
                "emoji_count": {"value": 0, "confidence": confidence, "source": source},
                "hashtag_count": {"value": 0, "confidence": confidence, "source": source},
            }

        # textstat-powered metrics
        flesch = textstat.flesch_reading_ease(text)
        avg_sent_len = textstat.words_per_sentence(text)
        syll_per_word = textstat.avg_syllables_per_word(text)
        lexicon = textstat.lexicon_count(text)
        sent_count = textstat.sentence_count(text)

        # Standard Python metrics
        words = text.split()
        avg_word_length = (
            sum(len(w.strip(".,!?;:\"'")) for w in words) / len(words)
            if words
            else 0.0
        )

        excl_count = text.count("!")
        quest_count = text.count("?")
        exclamation_density = excl_count / sent_count if sent_count > 0 else 0.0
        question_density = quest_count / sent_count if sent_count > 0 else 0.0

        emoji_count = sum(len(m) for m in _EMOJI_PATTERN.findall(text))
        hashtag_count = len(_HASHTAG_PATTERN.findall(text))

        return {
            "flesch_reading_ease": {"value": flesch, "confidence": confidence, "source": source},
            "avg_sentence_length": {"value": avg_sent_len, "confidence": confidence, "source": source},
            "syllable_count_per_word": {"value": syll_per_word, "confidence": confidence, "source": source},
            "lexicon_count": {"value": lexicon, "confidence": confidence, "source": source},
            "sentence_count": {"value": sent_count, "confidence": confidence, "source": source},
            "avg_word_length": {"value": round(avg_word_length, 2), "confidence": confidence, "source": source},
            "exclamation_density": {"value": round(exclamation_density, 2), "confidence": confidence, "source": source},
            "question_density": {"value": round(question_density, 2), "confidence": confidence, "source": source},
            "emoji_count": {"value": emoji_count, "confidence": confidence, "source": source},
            "hashtag_count": {"value": hashtag_count, "confidence": confidence, "source": source},
        }

    # -------------------------------------------------------------------------
    # Qualitative Dimension Defaults
    # -------------------------------------------------------------------------

    @staticmethod
    def get_qualitative_defaults() -> dict:
        """Return default structure for qualitative voice dimensions.

        Each dimension starts with null value, 0.0 confidence, and null source.
        Claude fills these at runtime via update_qualitative_dimensions().
        """
        return {
            dim: {"value": None, "confidence": 0.0, "source": None}
            for dim in QUALITATIVE_DIMENSIONS
        }

    # -------------------------------------------------------------------------
    # Profile Construction
    # -------------------------------------------------------------------------

    @staticmethod
    def build_voice_profile(db: Session, client_id: int) -> dict:
        """Build a complete voice profile from all materials for a client.

        Aggregates quantitative metrics across all materials, merges with existing
        qualitative dimensions (or defaults), and computes overall confidence.
        """
        materials = VoiceService.get_materials(db, client_id)

        if not materials:
            raise VoiceExtractionError(
                message="No voice materials found for this client",
                detail=f"client_id={client_id}",
                suggestion="Add source materials first with add_material()",
            )

        # Aggregate quantitative metrics across all materials
        all_texts = " ".join(m.content for m in materials)
        quantitative = VoiceService.compute_quantitative_metrics(all_texts)

        # Load existing qualitative dimensions or defaults
        existing_profile = (
            db.query(VoiceProfile)
            .filter(VoiceProfile.client_id == client_id)
            .first()
        )
        if existing_profile and existing_profile.profile_data:
            qualitative = {}
            base_voice = existing_profile.profile_data.get("base_voice", {})
            for dim in QUALITATIVE_DIMENSIONS:
                if dim in base_voice:
                    qualitative[dim] = base_voice[dim]
                else:
                    qualitative[dim] = {"value": None, "confidence": 0.0, "source": None}
        else:
            qualitative = VoiceService.get_qualitative_defaults()

        # Merge quantitative + qualitative into base_voice
        base_voice = {}
        base_voice.update(quantitative)
        base_voice.update(qualitative)

        # Platform variants with default deltas
        platform_variants = {
            "facebook": {"formality_delta": -0.1, "emoji_delta": 0.1},
            "instagram": {"formality_delta": -0.2, "hashtag_delta": 0.3},
        }

        # Compute overall confidence
        overall_confidence = VoiceService._compute_overall_confidence(
            quantitative, qualitative
        )

        now = datetime.now(timezone.utc).isoformat()

        profile = {
            "base_voice": base_voice,
            "platform_variants": platform_variants,
            "overall_confidence": round(overall_confidence, 2),
            "last_updated": now,
            "sample_count": len(materials),
        }

        return profile

    @staticmethod
    def save_voice_profile(
        db: Session, client_id: int, profile_data: dict
    ) -> VoiceProfile:
        """Create or update the VoiceProfile for a client.

        Sets confidence, sample count, calibration timestamp, logs the change,
        and triggers profile completeness recalculation if ClientService is available.
        """
        existing = (
            db.query(VoiceProfile)
            .filter(VoiceProfile.client_id == client_id)
            .first()
        )

        before_snapshot = None
        action = "voice.extracted"

        if existing:
            before_snapshot = {
                "profile_data": existing.profile_data,
                "overall_confidence_pct": existing.overall_confidence_pct,
                "sample_count": existing.sample_count,
            }
            action = "voice.updated"
            existing.profile_data = profile_data
            existing.overall_confidence_pct = int(
                profile_data.get("overall_confidence", 0) * 100
            )
            existing.sample_count = profile_data.get("sample_count", 0)
            existing.last_calibrated_at = datetime.now(timezone.utc)
            voice_profile = existing
        else:
            voice_profile = VoiceProfile(
                client_id=client_id,
                profile_data=profile_data,
                overall_confidence_pct=int(
                    profile_data.get("overall_confidence", 0) * 100
                ),
                sample_count=profile_data.get("sample_count", 0),
                last_calibrated_at=datetime.now(timezone.utc),
            )
            db.add(voice_profile)

        db.flush()

        # Audit log
        audit = AuditLog(
            client_id=client_id,
            action=action,
            actor="sophia",
            details={"sample_count": voice_profile.sample_count},
            before_snapshot=before_snapshot,
            after_snapshot={
                "profile_data": profile_data,
                "overall_confidence_pct": voice_profile.overall_confidence_pct,
                "sample_count": voice_profile.sample_count,
            },
        )
        db.add(audit)

        # Trigger profile completeness update if ClientService is available
        # (ClientService is from plan 01-02; may not exist yet)
        VoiceService._update_completeness(db, client_id)

        db.commit()

        return voice_profile

    # -------------------------------------------------------------------------
    # Qualitative Dimension Updates (called by Claude at runtime)
    # -------------------------------------------------------------------------

    @staticmethod
    def update_qualitative_dimensions(
        db: Session, client_id: int, dimensions: dict
    ) -> VoiceProfile:
        """Update qualitative voice dimensions from Claude's analysis.

        Merges the provided dimensions into the existing profile_data.base_voice,
        preserving computed quantitative metrics. Recalculates overall confidence
        and saves.
        """
        existing = (
            db.query(VoiceProfile)
            .filter(VoiceProfile.client_id == client_id)
            .first()
        )

        if not existing or not existing.profile_data:
            raise VoiceExtractionError(
                message="No voice profile exists to update",
                detail=f"client_id={client_id}",
                suggestion="Build a voice profile first with build_voice_profile()",
            )

        profile_data = dict(existing.profile_data)
        base_voice = dict(profile_data.get("base_voice", {}))

        # Merge qualitative dimensions (preserve quantitative metrics)
        for dim_name, dim_data in dimensions.items():
            if dim_name in QUALITATIVE_DIMENSIONS:
                base_voice[dim_name] = {
                    "value": dim_data.get("value"),
                    "confidence": dim_data.get("confidence", 0.0),
                    "source": dim_data.get("source", "claude_analysis"),
                }

        profile_data["base_voice"] = base_voice

        # Recalculate overall confidence
        quantitative = {
            k: v for k, v in base_voice.items() if k not in QUALITATIVE_DIMENSIONS
        }
        qualitative = {
            k: v for k, v in base_voice.items() if k in QUALITATIVE_DIMENSIONS
        }
        profile_data["overall_confidence"] = round(
            VoiceService._compute_overall_confidence(quantitative, qualitative), 2
        )
        profile_data["last_updated"] = datetime.now(timezone.utc).isoformat()

        # Audit log for qualitative update
        audit = AuditLog(
            client_id=client_id,
            action="voice.qualitative_updated",
            actor="sophia",
            details={
                "dimensions_updated": list(dimensions.keys()),
            },
        )
        db.add(audit)

        return VoiceService.save_voice_profile(db, client_id, profile_data)

    # -------------------------------------------------------------------------
    # Confidence Explanation
    # -------------------------------------------------------------------------

    @staticmethod
    def explain_confidence(confidence_pct: int) -> str:
        """Return a plain English explanation of the confidence percentage.

        Ranges:
            0-20%:  Very little to work with
            21-40%: Rough sense of tone
            41-60%: Working understanding
            61-80%: Solid grasp
            81-100%: Highly confident
        """
        if confidence_pct <= 20:
            return (
                "I have very little to work with. I need more source materials "
                "to understand this client's voice."
            )
        elif confidence_pct <= 40:
            return (
                "I have a rough sense of their tone but need more approved "
                "content to be confident."
            )
        elif confidence_pct <= 60:
            return (
                "I have a working understanding of their voice. More materials "
                "will sharpen the details."
            )
        elif confidence_pct <= 80:
            return (
                "I have a solid grasp of their voice profile. Fine-tuning from "
                "approved content will improve precision."
            )
        else:
            return (
                "I'm highly confident in this voice profile. It's well-calibrated "
                "from multiple sources."
            )

    # -------------------------------------------------------------------------
    # No-Content Fallback
    # -------------------------------------------------------------------------

    @staticmethod
    def create_fallback_profile(
        db: Session,
        client_id: int,
        industry: str,
        operator_description: str = "",
    ) -> dict:
        """Build a minimal fallback profile when no content materials exist.

        If operator_description is provided, it's stored as a VoiceMaterial and
        qualitative dimensions get slightly higher confidence (0.25 vs 0.15).
        """
        base_confidence = 0.15

        if operator_description:
            # Store as a material for provenance
            material_data = VoiceMaterialCreate(
                client_id=client_id,
                source_type="operator_description",
                content=operator_description,
                metadata_={"fallback": True, "industry": industry},
            )
            VoiceService.add_material(db, material_data)
            base_confidence = 0.25

        # Quantitative: all zero/null
        quantitative = {
            "flesch_reading_ease": {"value": 0.0, "confidence": 0.0, "source": None},
            "avg_sentence_length": {"value": 0.0, "confidence": 0.0, "source": None},
            "syllable_count_per_word": {"value": 0.0, "confidence": 0.0, "source": None},
            "lexicon_count": {"value": 0, "confidence": 0.0, "source": None},
            "sentence_count": {"value": 0, "confidence": 0.0, "source": None},
            "avg_word_length": {"value": 0.0, "confidence": 0.0, "source": None},
            "exclamation_density": {"value": 0.0, "confidence": 0.0, "source": None},
            "question_density": {"value": 0.0, "confidence": 0.0, "source": None},
            "emoji_count": {"value": 0, "confidence": 0.0, "source": None},
            "hashtag_count": {"value": 0, "confidence": 0.0, "source": None},
        }

        # Qualitative: industry-default placeholders with low confidence
        qualitative = {
            dim: {
                "value": f"{industry}-default",
                "confidence": base_confidence,
                "source": "industry_default",
            }
            for dim in QUALITATIVE_DIMENSIONS
        }

        base_voice = {}
        base_voice.update(quantitative)
        base_voice.update(qualitative)

        platform_variants = {
            "facebook": {"formality_delta": -0.1, "emoji_delta": 0.1},
            "instagram": {"formality_delta": -0.2, "hashtag_delta": 0.3},
        }

        # Overall confidence: only qualitative has any confidence
        # Quantitative all have 0.0, so only qualitative contributes
        overall_confidence = base_confidence * QUALITATIVE_WEIGHT

        now = datetime.now(timezone.utc).isoformat()
        material_count = 1 if operator_description else 0

        profile = {
            "base_voice": base_voice,
            "platform_variants": platform_variants,
            "overall_confidence": round(overall_confidence, 2),
            "last_updated": now,
            "sample_count": material_count,
        }

        return profile

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _compute_overall_confidence(
        quantitative: dict, qualitative: dict
    ) -> float:
        """Compute weighted average confidence across all dimensions.

        Quantitative metrics (computed): weight 0.3
        Qualitative dimensions (Claude-extracted): weight 0.7
        Only dimensions with confidence > 0 are included.
        """
        quant_confidences = [
            v["confidence"]
            for v in quantitative.values()
            if isinstance(v, dict) and v.get("confidence", 0) > 0
        ]
        qual_confidences = [
            v["confidence"]
            for v in qualitative.values()
            if isinstance(v, dict) and v.get("confidence", 0) > 0
        ]

        quant_avg = (
            sum(quant_confidences) / len(quant_confidences) if quant_confidences else 0.0
        )
        qual_avg = (
            sum(qual_confidences) / len(qual_confidences) if qual_confidences else 0.0
        )

        # If only one category has data, use it at full weight
        if quant_avg > 0 and qual_avg > 0:
            return quant_avg * QUANTITATIVE_WEIGHT + qual_avg * QUALITATIVE_WEIGHT
        elif quant_avg > 0:
            return quant_avg * QUANTITATIVE_WEIGHT
        elif qual_avg > 0:
            return qual_avg * QUALITATIVE_WEIGHT
        else:
            return 0.0

    @staticmethod
    def _update_completeness(db: Session, client_id: int) -> None:
        """Update client profile completeness after voice profile changes.

        Uses ClientService.compute_profile_completeness() which takes a Client
        object and optional db session, returning (pct, mvp_ready).
        """
        client = db.query(Client).filter(Client.id == client_id).first()
        if not client:
            return

        try:
            from sophia.intelligence.service import ClientService

            pct, mvp_ready = ClientService.compute_profile_completeness(
                client, db=db
            )
            client.profile_completeness_pct = pct
            client.is_mvp_ready = mvp_ready
        except (ImportError, AttributeError):
            # ClientService not yet implemented (plan 01-02).
            # Basic heuristic: voice profile existence = at least 20% completeness.
            current = client.profile_completeness_pct or 0
            if current < 20:
                client.profile_completeness_pct = 20
