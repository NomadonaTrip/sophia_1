"""Stylometric voice alignment service: feature extraction, baseline
computation, and drift scoring.

Uses spaCy for POS tagging and sentence segmentation, textstat for
readability metrics. Detects voice drift by comparing draft features
against a baseline computed from the last 20-30 approved posts.

FR19 default thresholds:
  - avg_sentence_length: 0.25 (25% deviation)
  - vocabulary_richness: 0.20 (20% deviation)
  - all others: 0.30 (30% deviation)
"""

from __future__ import annotations

import logging
import statistics
from typing import Optional

import spacy
import textstat

logger = logging.getLogger(__name__)

# Load spaCy model at module level for reuse
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    logger.warning(
        "spaCy en_core_web_sm model not found. "
        "Run: python -m spacy download en_core_web_sm"
    )
    nlp = None

# Feature names for the 9-feature stylometric vector
FEATURE_NAMES = (
    "avg_sentence_length",
    "sentence_length_std",
    "avg_word_length",
    "vocabulary_richness",
    "noun_ratio",
    "verb_ratio",
    "adj_ratio",
    "flesch_reading_ease",
    "avg_syllables_per_word",
)

# FR19 default deviation thresholds (percentage of baseline mean)
DEFAULT_THRESHOLDS: dict[str, float] = {
    "avg_sentence_length": 0.25,
    "vocabulary_richness": 0.20,
    "sentence_length_std": 0.30,
    "avg_word_length": 0.30,
    "noun_ratio": 0.30,
    "verb_ratio": 0.30,
    "adj_ratio": 0.30,
    "flesch_reading_ease": 0.30,
    "avg_syllables_per_word": 0.30,
}

# Stories get more permissive thresholds (short text = higher natural variance)
STORY_THRESHOLD_MULTIPLIER = 1.5


def extract_stylometric_features(text: str) -> dict[str, float]:
    """Extract 9 stylometric features from text using spaCy + textstat.

    Features:
        avg_sentence_length: mean token count per sentence
        sentence_length_std: std of sentence token counts
        avg_word_length: mean char count per word (excl punctuation/space)
        vocabulary_richness: unique lemmas / total words (type-token ratio)
        noun_ratio: proportion of NOUN POS tags
        verb_ratio: proportion of VERB POS tags
        adj_ratio: proportion of ADJ POS tags
        flesch_reading_ease: via textstat
        avg_syllables_per_word: via textstat

    Args:
        text: Input text to analyze.

    Returns:
        Dict mapping feature name to float value. All zeros for empty text.
    """
    zeros = {name: 0.0 for name in FEATURE_NAMES}

    if not text or not text.strip():
        return zeros

    if nlp is None:
        logger.error("spaCy model not loaded, returning zeros")
        return zeros

    doc = nlp(text)

    # Sentence-level features
    sentences = list(doc.sents)
    if not sentences:
        return zeros

    sent_lengths = [len(sent) for sent in sentences]
    avg_sentence_length = statistics.mean(sent_lengths)
    sentence_length_std = (
        statistics.stdev(sent_lengths) if len(sent_lengths) > 1 else 0.0
    )

    # Word-level features (exclude punctuation and whitespace tokens)
    words = [token for token in doc if not token.is_punct and not token.is_space]
    if not words:
        return zeros

    word_count = len(words)
    avg_word_length = statistics.mean(len(token.text) for token in words)

    # Vocabulary richness (type-token ratio using lemmas)
    unique_lemmas = set(token.lemma_.lower() for token in words)
    vocabulary_richness = len(unique_lemmas) / word_count if word_count > 0 else 0.0

    # POS ratios
    noun_count = sum(1 for token in words if token.pos_ == "NOUN")
    verb_count = sum(1 for token in words if token.pos_ == "VERB")
    adj_count = sum(1 for token in words if token.pos_ == "ADJ")

    noun_ratio = noun_count / word_count if word_count > 0 else 0.0
    verb_ratio = verb_count / word_count if word_count > 0 else 0.0
    adj_ratio = adj_count / word_count if word_count > 0 else 0.0

    # textstat metrics
    flesch = textstat.flesch_reading_ease(text)
    avg_syll = textstat.avg_syllables_per_word(text)

    return {
        "avg_sentence_length": avg_sentence_length,
        "sentence_length_std": sentence_length_std,
        "avg_word_length": avg_word_length,
        "vocabulary_richness": vocabulary_richness,
        "noun_ratio": noun_ratio,
        "verb_ratio": verb_ratio,
        "adj_ratio": adj_ratio,
        "flesch_reading_ease": flesch,
        "avg_syllables_per_word": avg_syll,
    }


def compute_voice_baseline(
    approved_posts: list[str],
) -> dict[str, tuple[float, float]]:
    """Compute per-feature mean and std from approved posts.

    Args:
        approved_posts: List of approved post text strings.

    Returns:
        Dict mapping feature name to (mean, std) tuple.
        Empty dict if no posts provided.
    """
    if not approved_posts:
        return {}

    if len(approved_posts) < 5:
        logger.warning(
            "Only %d approved posts provided for baseline. "
            "Recommend 5+ posts for reliable voice baseline.",
            len(approved_posts),
        )

    # Extract features for each post
    all_features: list[dict[str, float]] = []
    for post in approved_posts:
        features = extract_stylometric_features(post)
        all_features.append(features)

    if not all_features:
        return {}

    # Compute mean and std per feature
    baseline: dict[str, tuple[float, float]] = {}
    for name in FEATURE_NAMES:
        values = [f[name] for f in all_features]
        mean = statistics.mean(values)
        std = statistics.stdev(values) if len(values) > 1 else 0.0
        baseline[name] = (mean, std)

    return baseline


def score_voice_alignment(
    draft_text: str,
    baseline: dict[str, tuple[float, float]],
    thresholds: Optional[dict[str, float]] = None,
    is_story: bool = False,
) -> tuple[float, list[str]]:
    """Score how well a draft aligns with the voice baseline.

    Computes percentage deviation from baseline mean per feature.
    Features exceeding their threshold are flagged as deviations.

    Args:
        draft_text: Text of the draft to score.
        baseline: Baseline from compute_voice_baseline().
        thresholds: Optional custom thresholds. Uses FR19 defaults if None.
        is_story: If True, applies 1.5x permissive threshold multiplier.

    Returns:
        Tuple of (alignment_score, deviations_list).
        alignment_score: 0.0 to 1.0 (proportion of features within threshold).
        deviations_list: Human-readable descriptions of deviating features.
    """
    # Cold start: empty baseline returns neutral score
    if not baseline:
        return (0.5, ["Insufficient baseline data"])

    effective_thresholds = dict(thresholds or DEFAULT_THRESHOLDS)

    # Stories get more permissive thresholds
    if is_story:
        effective_thresholds = {
            k: v * STORY_THRESHOLD_MULTIPLIER
            for k, v in effective_thresholds.items()
        }

    draft_features = extract_stylometric_features(draft_text)
    deviations: list[str] = []
    features_checked = 0
    features_within = 0

    for name in FEATURE_NAMES:
        if name not in baseline:
            continue

        base_mean, _base_std = baseline[name]
        draft_value = draft_features.get(name, 0.0)
        threshold = effective_thresholds.get(name, 0.30)

        features_checked += 1

        # Compute percentage deviation from baseline mean
        if abs(base_mean) < 1e-9:
            # Baseline mean is ~zero; use absolute deviation check
            if abs(draft_value) > threshold:
                deviations.append(
                    f"{name}: draft={draft_value:.2f}, baseline=~0, "
                    f"exceeds threshold {threshold:.0%}"
                )
            else:
                features_within += 1
        else:
            pct_deviation = abs(draft_value - base_mean) / abs(base_mean)
            if pct_deviation > threshold:
                deviations.append(
                    f"{name}: draft={draft_value:.2f}, baseline={base_mean:.2f}, "
                    f"deviation={pct_deviation:.0%} > {threshold:.0%}"
                )
            else:
                features_within += 1

    alignment_score = (
        features_within / features_checked if features_checked > 0 else 0.5
    )

    return (alignment_score, deviations)


def compute_voice_confidence(approved_count: int) -> str:
    """Determine voice confidence level from approved post count.

    Confidence levels (visible to operator per draft):
        < 5 approved posts: "low"
        5-15 approved posts: "medium"
        16+ approved posts: "high"

    Args:
        approved_count: Number of approved posts in history.

    Returns:
        Confidence level string: "low", "medium", or "high".
    """
    if approved_count < 5:
        return "low"
    elif approved_count <= 15:
        return "medium"
    else:
        return "high"
