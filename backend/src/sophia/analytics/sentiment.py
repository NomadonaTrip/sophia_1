"""VADER-based comment sentiment analysis.

Analyzes comment sentiment per post and stores results as
EngagementMetric with metric_name="comment_quality_score".

Uses lazy import for VADER to avoid slow NTFS startup (WSL2 pattern).
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from sophia.analytics.models import EngagementMetric

logger = logging.getLogger(__name__)


def analyze_comment_sentiment(comments: list[str]) -> dict:
    """Analyze sentiment of a list of comments using VADER.

    Lazy-imports vaderSentiment inside function body to avoid
    slow NTFS imports at module load time.

    Thresholds:
    - compound >= 0.05 = positive
    - compound <= -0.05 = negative
    - else neutral

    Args:
        comments: List of comment text strings.

    Returns:
        Dict with positive_pct, negative_pct, neutral_pct,
        avg_compound, and total_comments.
    """
    if not comments:
        return {
            "positive_pct": 0.0,
            "negative_pct": 0.0,
            "neutral_pct": 0.0,
            "avg_compound": 0.0,
            "total_comments": 0,
        }

    # Lazy import (NTFS pattern)
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

    analyzer = SentimentIntensityAnalyzer()

    positive = 0
    negative = 0
    neutral = 0
    compound_sum = 0.0

    for comment in comments:
        scores = analyzer.polarity_scores(comment)
        compound = scores["compound"]
        compound_sum += compound

        if compound >= 0.05:
            positive += 1
        elif compound <= -0.05:
            negative += 1
        else:
            neutral += 1

    total = len(comments)
    avg_compound = round(compound_sum / total, 3)

    return {
        "positive_pct": round(positive / total * 100, 1),
        "negative_pct": round(negative / total * 100, 1),
        "neutral_pct": round(neutral / total * 100, 1),
        "avg_compound": avg_compound,
        "total_comments": total,
    }


def analyze_post_sentiment(
    db: Session,
    content_draft_id: int,
    comments: list[str],
) -> dict:
    """Analyze comments for a specific post and store result.

    Stores avg_compound as an EngagementMetric with
    metric_name="comment_quality_score".

    Args:
        db: SQLAlchemy session.
        content_draft_id: The post to analyze.
        comments: List of comment texts.

    Returns:
        Full sentiment breakdown dict.
    """
    from datetime import date

    sentiment = analyze_comment_sentiment(comments)

    if sentiment["total_comments"] > 0:
        # Look up the draft to get client_id
        from sophia.content.models import ContentDraft

        draft = db.get(ContentDraft, content_draft_id)
        if draft:
            metric = EngagementMetric(
                client_id=draft.client_id,
                content_draft_id=content_draft_id,
                platform=draft.platform,
                metric_name="comment_quality_score",
                metric_value=sentiment["avg_compound"],
                metric_date=date.today(),
                is_algorithm_dependent=False,
                period="day",
            )
            db.add(metric)
            db.flush()

            logger.info(
                "Stored comment_quality_score=%.3f for draft %d (%d comments)",
                sentiment["avg_compound"],
                content_draft_id,
                sentiment["total_comments"],
            )

    return sentiment
