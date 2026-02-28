"""Statistical anomaly detection for engagement metrics.

Uses modified z-score with Median Absolute Deviation (MAD), consistent
with the Phase 2 algorithm.py approach. Detects unusual spikes or drops
in per-client metrics.

Does NOT use numpy/scipy -- uses stdlib statistics for lighter dependency.
"""

from __future__ import annotations

import logging
import statistics
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from sophia.analytics.models import EngagementMetric

logger = logging.getLogger(__name__)


def detect_metric_anomaly(
    values: list[float],
    current_value: float,
    threshold: float = 2.5,
) -> Optional[dict]:
    """Detect if current_value is anomalous relative to historical values.

    Uses modified z-score: 0.6745 * (value - median) / MAD.
    Requires at least 7 data points for reliable detection.
    MAD = 0 returns None (identical values, no anomaly to detect).

    Args:
        values: Historical values (at least 7 required).
        current_value: The most recent value to test.
        threshold: Modified z-score threshold (default 2.5).

    Returns:
        Anomaly dict with direction, z_score, severity, or None.
    """
    if len(values) < 7:
        return None

    median_val = statistics.median(values)

    # Compute MAD (Median Absolute Deviation)
    deviations = [abs(v - median_val) for v in values]
    mad = statistics.median(deviations)

    # MAD of zero means all values are identical -- no anomaly to detect
    if mad == 0.0:
        return None

    # Modified z-score
    z_score = 0.6745 * (current_value - median_val) / mad

    if abs(z_score) <= threshold:
        return None

    direction = "spike" if z_score > 0 else "drop"
    severity = "high" if abs(z_score) > 4 else "medium"

    return {
        "anomaly": True,
        "direction": direction,
        "z_score": round(z_score, 3),
        "current": current_value,
        "median": round(median_val, 3),
        "severity": severity,
    }


def detect_client_anomalies(
    db: Session, client_id: int
) -> list[dict]:
    """Detect anomalies across all metric types for a client.

    For each metric_name with >= 7 data points in the last 30 days,
    uses the most recent value as current_value and the rest as history.

    Args:
        db: SQLAlchemy session.
        client_id: Client to check for anomalies.

    Returns:
        List of anomaly dicts with metric_name added to each.
    """
    cutoff = date.today() - timedelta(days=30)

    # Get distinct metric names with enough data
    metric_names = (
        db.query(EngagementMetric.metric_name)
        .filter(
            EngagementMetric.client_id == client_id,
            EngagementMetric.metric_date >= cutoff,
        )
        .group_by(EngagementMetric.metric_name)
        .having(func.count(EngagementMetric.id) >= 7)
        .all()
    )

    anomalies = []
    for (metric_name,) in metric_names:
        # Get values ordered by date
        rows = (
            db.query(EngagementMetric.metric_value)
            .filter(
                EngagementMetric.client_id == client_id,
                EngagementMetric.metric_name == metric_name,
                EngagementMetric.metric_date >= cutoff,
            )
            .order_by(EngagementMetric.metric_date.asc())
            .all()
        )

        values = [r[0] for r in rows]
        if len(values) < 8:
            # Need at least 7 history + 1 current
            continue

        current = values[-1]
        history = values[:-1]

        result = detect_metric_anomaly(history, current)
        if result:
            result["metric_name"] = metric_name
            anomalies.append(result)

    logger.info(
        "Detected %d anomalies for client %d", len(anomalies), client_id
    )

    return anomalies


def detect_portfolio_anomalies(db: Session) -> list[dict]:
    """Detect anomalies across all clients.

    Runs detect_client_anomalies for every active client.
    Used for morning brief attention flags.

    Args:
        db: SQLAlchemy session.

    Returns:
        Combined list of anomaly dicts with client_id added.
    """
    from sophia.intelligence.models import Client

    clients = (
        db.query(Client)
        .filter_by(is_archived=False)
        .all()
    )

    all_anomalies = []
    for client in clients:
        client_anomalies = detect_client_anomalies(db, client.id)
        for a in client_anomalies:
            a["client_id"] = client.id
            a["client_name"] = client.name
        all_anomalies.extend(client_anomalies)

    logger.info(
        "Portfolio anomaly scan: %d anomalies across %d clients",
        len(all_anomalies),
        len(clients),
    )

    return all_anomalies
