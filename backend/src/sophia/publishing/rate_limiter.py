"""Per-platform rate limit tracking using sliding window.

Facebook: 200 calls/hour
Instagram: 25 posts/day (conservative default)

Rate limits are tracked in-memory. In production, these persist across
restarts via the publishing queue's retry/scheduling logic.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


class RateLimiter:
    """Per-platform rate limit tracking using sliding window."""

    def __init__(self) -> None:
        self._calls: dict[str, list[datetime]] = {"facebook": [], "instagram": []}
        self._limits: dict[str, dict] = {
            "facebook": {"max_calls": 200, "window": timedelta(hours=1)},
            "instagram": {"max_calls": 25, "window": timedelta(hours=24)},
        }

    def _prune(self, platform: str) -> None:
        """Remove calls outside the sliding window."""
        config = self._limits.get(platform)
        if not config:
            return
        cutoff = datetime.now(timezone.utc) - config["window"]
        self._calls[platform] = [
            t for t in self._calls.get(platform, []) if t > cutoff
        ]

    def can_publish(self, platform: str) -> bool:
        """Check if publishing is allowed within rate limits."""
        self._prune(platform)
        config = self._limits.get(platform)
        if not config:
            return True  # Unknown platform -- allow
        return len(self._calls.get(platform, [])) < config["max_calls"]

    def record_call(self, platform: str) -> None:
        """Record an API call for rate tracking."""
        if platform not in self._calls:
            self._calls[platform] = []
        self._calls[platform].append(datetime.now(timezone.utc))

    def next_available(self, platform: str) -> datetime:
        """Return the next time publishing is allowed.

        If currently allowed, returns now. Otherwise returns when the
        oldest call in the window will expire.
        """
        self._prune(platform)
        config = self._limits.get(platform)
        if not config:
            return datetime.now(timezone.utc)

        calls = self._calls.get(platform, [])
        if len(calls) < config["max_calls"]:
            return datetime.now(timezone.utc)

        # Oldest call + window = when it expires
        oldest = min(calls)
        return oldest + config["window"]


# Module-level singleton
rate_limiter = RateLimiter()
