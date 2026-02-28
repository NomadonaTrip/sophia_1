"""Meta Graph API metric collector.

Pulls engagement metrics from Meta Graph API v22 for all published posts.
Persists as EngagementMetric rows tagged by algorithm dependency.
Daily collection scheduled via APScheduler at 6 AM operator timezone.

All HTTP calls use httpx.AsyncClient. For APScheduler bridge, uses
the same async-in-sync pattern as publishing/executor.py.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional

import httpx
from sqlalchemy.orm import Session

from sophia.analytics.models import ALGO_DEPENDENT, EngagementMetric
from sophia.approval.models import PublishingQueueEntry
from sophia.config import Settings

logger = logging.getLogger(__name__)

# Meta Graph API v22 metric names (post-deprecation migration)
INSTAGRAM_POST_METRICS = "views,reach,saved,shares,comments,likes"
INSTAGRAM_STORY_METRICS = "views,reach,replies,shares"
INSTAGRAM_REEL_METRICS = "views,reach,saved,shares,comments,likes,plays"
FACEBOOK_POST_METRICS = "post_reactions_by_type_total,post_clicks,post_impressions"

# Page-level metrics (pulled once per client per day)
INSTAGRAM_PAGE_METRICS = "views,reach,follower_count,profile_activity"
FACEBOOK_PAGE_METRICS = "page_views_total,page_fan_adds_unique"

# Graph API base URL
GRAPH_API_BASE = "https://graph.facebook.com/v22.0"


def _classify_metric(metric_name: str) -> bool:
    """Return True if metric_name is algorithm-dependent.

    Algorithm-dependent metrics (reach, views, impressions) are determined
    by platform algorithms. Algorithm-independent metrics (likes, saves,
    shares) require conscious user action.
    """
    return metric_name.lower() in ALGO_DEPENDENT


def _convert_api_response_to_metrics(
    api_data: dict,
    client_id: int,
    platform: str,
    content_draft_id: int | None,
    platform_post_id: str | None,
    operator_tz: str,
) -> list[EngagementMetric]:
    """Parse Meta API response format into flat EngagementMetric rows.

    Meta Graph API returns insights in the format:
    {"data": [{"name": "metric_name", "values": [{"value": N, "end_time": "..."}]}]}

    Converts UTC API dates to operator timezone for metric_date.
    """
    import zoneinfo

    metrics = []
    tz = zoneinfo.ZoneInfo(operator_tz)

    data_list = api_data.get("data", [])
    for item in data_list:
        metric_name = item.get("name", "")
        values = item.get("values", [])

        for val_entry in values:
            raw_value = val_entry.get("value")
            if raw_value is None:
                continue

            # Handle reaction breakdowns (dict values like {LIKE: 5, LOVE: 2})
            if isinstance(raw_value, dict):
                # Flatten reaction types into separate metrics
                for reaction_type, count in raw_value.items():
                    sub_name = f"{metric_name}_{reaction_type.lower()}"
                    end_time_str = val_entry.get("end_time", "")
                    metric_date = _parse_api_date(end_time_str, tz)

                    metrics.append(EngagementMetric(
                        client_id=client_id,
                        content_draft_id=content_draft_id,
                        platform=platform,
                        metric_name=sub_name,
                        metric_value=float(count),
                        metric_date=metric_date,
                        is_algorithm_dependent=_classify_metric(sub_name),
                        period="day",
                        platform_post_id=platform_post_id,
                    ))
            else:
                end_time_str = val_entry.get("end_time", "")
                metric_date = _parse_api_date(end_time_str, tz)

                metrics.append(EngagementMetric(
                    client_id=client_id,
                    content_draft_id=content_draft_id,
                    platform=platform,
                    metric_name=metric_name,
                    metric_value=float(raw_value),
                    metric_date=metric_date,
                    is_algorithm_dependent=_classify_metric(metric_name),
                    period="day",
                    platform_post_id=platform_post_id,
                ))

    return metrics


def _parse_api_date(end_time_str: str, tz: Any) -> date:
    """Parse Meta API end_time string to date in operator timezone.

    Falls back to today in operator timezone if parsing fails.
    """
    if end_time_str:
        try:
            dt_utc = datetime.fromisoformat(
                end_time_str.replace("Z", "+00:00")
            )
            return dt_utc.astimezone(tz).date()
        except (ValueError, TypeError):
            pass

    return datetime.now(tz).date()


async def _pull_instagram_post_metrics(
    post_id: str, access_token: str
) -> dict:
    """Pull insights for a single Instagram post via Graph API v22.

    Returns parsed JSON response or empty dict on error.
    """
    url = f"{GRAPH_API_BASE}/{post_id}/insights"
    params = {
        "metric": INSTAGRAM_POST_METRICS,
        "access_token": access_token,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()


async def _pull_facebook_post_metrics(
    post_id: str, access_token: str
) -> dict:
    """Pull insights for a single Facebook post via Graph API v22.

    Returns parsed JSON response or empty dict on error.
    """
    url = f"{GRAPH_API_BASE}/{post_id}/insights"
    params = {
        "metric": FACEBOOK_POST_METRICS,
        "access_token": access_token,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()


async def _pull_page_metrics(
    page_id: str,
    platform: str,
    access_token: str,
    since: date,
    until: date,
) -> dict:
    """Pull page-level insights for a date range.

    Returns parsed JSON response or empty dict on error.
    """
    url = f"{GRAPH_API_BASE}/{page_id}/insights"
    metrics = (
        INSTAGRAM_PAGE_METRICS
        if platform == "instagram"
        else FACEBOOK_PAGE_METRICS
    )
    params = {
        "metric": metrics,
        "since": since.isoformat(),
        "until": until.isoformat(),
        "period": "day",
        "access_token": access_token,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()


async def pull_client_metrics(
    db: Session,
    client_id: int,
    settings: Settings,
) -> list[EngagementMetric]:
    """Pull page-level and post-level metrics for a single client.

    Steps:
    1. Query published posts from PublishingQueueEntry
    2. Pull page-level metrics (incremental, since yesterday)
    3. Pull per-post metrics for each published post
    4. Convert to EngagementMetric objects, tag algorithm dependency
    5. Persist to DB
    6. Return list of created metrics

    Handles 401/403 (token errors), 429 (rate limits), and other errors
    gracefully -- returns empty/partial list, never raises.
    """
    all_metrics: list[EngagementMetric] = []
    today = date.today()
    yesterday = today - timedelta(days=1)
    operator_tz = settings.operator_timezone

    # Get published posts for this client
    published_entries = (
        db.query(PublishingQueueEntry)
        .filter_by(client_id=client_id, status="published")
        .filter(PublishingQueueEntry.platform_post_id.isnot(None))
        .all()
    )

    # Pull page-level metrics for each platform
    for platform_name, token, page_id in [
        ("facebook", settings.facebook_access_token, settings.facebook_page_id),
        ("instagram", settings.instagram_access_token, settings.instagram_business_account_id),
    ]:
        if not token or not page_id:
            continue

        try:
            page_data = await _pull_page_metrics(
                page_id, platform_name, token, yesterday, today
            )
            page_metrics = _convert_api_response_to_metrics(
                page_data,
                client_id=client_id,
                platform=platform_name,
                content_draft_id=None,
                platform_post_id=None,
                operator_tz=operator_tz,
            )
            all_metrics.extend(page_metrics)
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                logger.error(
                    "Token error for %s (client %d): %s",
                    platform_name, client_id, e,
                )
                return []
            elif e.response.status_code == 429:
                logger.warning(
                    "Rate limited on %s page metrics (client %d)",
                    platform_name, client_id,
                )
                # Return what we have so far
                break
            else:
                logger.error(
                    "Error pulling %s page metrics (client %d): %s",
                    platform_name, client_id, e,
                )
                continue
        except Exception as e:
            logger.error(
                "Unexpected error pulling %s page metrics (client %d): %s",
                platform_name, client_id, e,
            )
            continue

    # Pull per-post metrics
    for entry in published_entries:
        platform = entry.platform
        post_id = entry.platform_post_id

        if platform == "instagram":
            token = settings.instagram_access_token
        else:
            token = settings.facebook_access_token

        if not token:
            continue

        try:
            if platform == "instagram":
                post_data = await _pull_instagram_post_metrics(post_id, token)
            else:
                post_data = await _pull_facebook_post_metrics(post_id, token)

            post_metrics = _convert_api_response_to_metrics(
                post_data,
                client_id=client_id,
                platform=platform,
                content_draft_id=entry.content_draft_id,
                platform_post_id=post_id,
                operator_tz=operator_tz,
            )
            all_metrics.extend(post_metrics)

        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                logger.error(
                    "Token error pulling post %s metrics: %s", post_id, e,
                )
                return all_metrics  # Return partial on auth error
            elif e.response.status_code == 429:
                logger.warning(
                    "Rate limited pulling post %s metrics", post_id,
                )
                break  # Return partial on rate limit
            else:
                logger.error(
                    "Error pulling post %s metrics: %s", post_id, e,
                )
                continue
        except Exception as e:
            logger.error(
                "Unexpected error pulling post %s metrics: %s", post_id, e,
            )
            continue

    # Persist all metrics
    if all_metrics:
        db.add_all(all_metrics)
        db.flush()

    logger.info(
        "Pulled %d metrics for client %d", len(all_metrics), client_id,
    )

    return all_metrics


async def pull_all_clients_metrics(
    db: Session,
    settings: Settings,
) -> dict[int, int]:
    """Pull metrics for all clients with valid platform tokens.

    Entry point for the daily APScheduler job.
    Returns dict of client_id -> metric_count.
    """
    from sophia.intelligence.models import Client

    clients = (
        db.query(Client)
        .filter_by(is_archived=False)
        .all()
    )

    results: dict[int, int] = {}
    for client in clients:
        try:
            metrics = await pull_client_metrics(db, client.id, settings)
            results[client.id] = len(metrics)
        except Exception as e:
            logger.error(
                "Error pulling metrics for client %d: %s", client.id, e,
            )
            results[client.id] = 0

    logger.info(
        "Daily metric pull complete: %d clients, %d total metrics",
        len(results), sum(results.values()),
    )

    return results


def register_daily_metric_pull(
    scheduler: Any,
    db_session_factory: Callable[[], Session],
    settings: Settings,
) -> None:
    """Register APScheduler job for daily metric pull at 6 AM operator timezone.

    Uses the same async-in-sync pattern as publishing/executor.py for
    the APScheduler thread bridge.

    Logs warnings if platform tokens are empty but does NOT raise.
    """
    import zoneinfo

    # Token health check on startup
    if not settings.facebook_access_token:
        logger.warning(
            "facebook_access_token is empty -- metric pull will skip Facebook"
        )
    if not settings.instagram_access_token:
        logger.warning(
            "instagram_access_token is empty -- metric pull will skip Instagram"
        )

    tz = zoneinfo.ZoneInfo(settings.operator_timezone)

    def _daily_metric_job():
        """Sync wrapper for async metric pull (APScheduler thread bridge)."""
        db = db_session_factory()
        try:
            asyncio.run(pull_all_clients_metrics(db, settings))
            db.commit()
        except Exception as e:
            logger.error("Daily metric pull failed: %s", e)
            db.rollback()
        finally:
            db.close()

    scheduler.add_job(
        _daily_metric_job,
        trigger="cron",
        hour=6,
        minute=0,
        timezone=tz,
        id="daily_metric_pull",
        replace_existing=True,
    )

    logger.info(
        "Daily metric pull registered (6:00 AM %s)", settings.operator_timezone,
    )
