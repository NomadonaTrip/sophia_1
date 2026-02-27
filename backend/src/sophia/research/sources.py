"""MCP source registry, ResearchScope per-client query builder, and circuit breaker.

Provides the infrastructure for querying external MCP servers (Google News,
Google Trends, Reddit, Bright Data, Firecrawl, Playwright) with per-source
circuit breakers to prevent cascade failures and per-client market scoping.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from sophia.intelligence.models import Client

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Track consecutive failures per MCP source.

    Opens after 5 consecutive failures. Cooldown is 5 minutes.
    When open, queries are skipped (returning None) until cooldown expires.
    """

    FAILURE_THRESHOLD = 5
    COOLDOWN_SECONDS = 300  # 5 minutes

    def __init__(self, name: str) -> None:
        self.name = name
        self.failure_count: int = 0
        self.last_failure_at: Optional[float] = None
        self._open: bool = False

    def record_success(self) -> None:
        """Reset failure tracking on successful query."""
        self.failure_count = 0
        self._open = False

    def record_failure(self) -> None:
        """Record a failure. Opens circuit after threshold reached."""
        self.failure_count += 1
        self.last_failure_at = time.time()
        if self.failure_count >= self.FAILURE_THRESHOLD:
            self._open = True
            logger.warning(
                "Circuit breaker OPEN for source '%s' after %d consecutive failures",
                self.name,
                self.failure_count,
            )

    def is_open(self) -> bool:
        """Check if circuit breaker is open (blocking queries).

        If cooldown has expired, auto-close (half-open state allows retry).
        """
        if not self._open:
            return False

        # Check cooldown
        if self.last_failure_at is not None:
            elapsed = time.time() - self.last_failure_at
            if elapsed >= self.COOLDOWN_SECONDS:
                logger.info(
                    "Circuit breaker cooldown expired for '%s', allowing retry",
                    self.name,
                )
                self._open = False
                self.failure_count = 0
                return False

        return True


class ResearchScope:
    """Build market-scoped query parameters from a Client profile.

    Initializes from client's market_scope JSON and direct fields.
    Produces scoped queries for news, trends, and community sources.
    """

    def __init__(self, client: Client) -> None:
        market_scope = client.market_scope or {}

        self.location: str = (
            market_scope.get("location")
            or client.geography_area
            or ""
        )
        self.radius: str = (
            market_scope.get("radius")
            or (f"{client.geography_radius_km}km" if client.geography_radius_km else "50km")
        )
        self.industry: str = (
            client.industry_vertical
            or client.industry
            or ""
        )
        self.blocklist: list[str] = (
            market_scope.get("source_blocklist")
            or []
        )
        self.content_pillars: list[str] = client.content_pillars or []
        self.client_id: int = client.id

    def scoped_news_query(self, topic: str) -> dict:
        """Google News query scoped by location.

        Returns query parameters for the google-news-trends MCP server.
        """
        return {
            "keyword": f"{topic} {self.location}".strip(),
            "location": self.location,
            "limit": 5,
        }

    def scoped_trends_query(self) -> dict:
        """Google Trends query for Ontario.

        Returns query parameters for trending topic discovery.
        """
        return {
            "geo": "CA-ON",
            "limit": 10,
        }

    def scoped_community_query(self, topic: str) -> dict:
        """Reddit/community query scoped by location and industry.

        Returns query parameters for community discussion sources.
        """
        return {
            "keyword": f"{topic} {self.industry} {self.location}".strip(),
            "subreddits": [f"r/{self.location.split(',')[0].strip().lower()}"]
            if self.location
            else [],
            "limit": 5,
        }

    def is_blocked(self, source_url: str) -> bool:
        """Check if a source URL is on the client's blocklist."""
        if not source_url or not self.blocklist:
            return False
        source_lower = source_url.lower()
        return any(blocked.lower() in source_lower for blocked in self.blocklist)


class MCPSourceRegistry:
    """Registry of available MCP servers with per-server circuit breakers.

    Manages registration, health tracking, and query dispatch for all
    MCP sources used by the research engine.
    """

    def __init__(self) -> None:
        self._sources: dict[str, dict] = {}
        self._breakers: dict[str, CircuitBreaker] = {}

    def register_source(self, name: str, server_config: dict) -> None:
        """Register an MCP source with its configuration.

        Args:
            name: Source identifier (e.g., 'google-news-trends', 'firecrawl').
            server_config: MCP server connection config.
        """
        self._sources[name] = server_config
        self._breakers[name] = CircuitBreaker(name)
        logger.info("Registered MCP source: %s", name)

    async def query_source(
        self,
        name: str,
        params: dict,
        scope: Optional[ResearchScope] = None,
    ) -> list[dict] | None:
        """Query a specific MCP source with circuit breaker protection.

        Checks circuit breaker first. On failure, records failure and returns
        None (partial research continues). On success, records success.
        Applies source blocklist filtering if scope provided.

        Args:
            name: Source name to query.
            params: Query parameters to send.
            scope: Optional ResearchScope for blocklist filtering.

        Returns:
            List of result dicts, or None if source unavailable/failed.
        """
        if name not in self._sources:
            logger.warning("Unknown MCP source: %s", name)
            return None

        breaker = self._breakers[name]
        if breaker.is_open():
            logger.debug(
                "Skipping source '%s' -- circuit breaker is open",
                name,
            )
            return None

        try:
            # Dispatch query to MCP server
            results = await self._dispatch_query(name, params)

            # Filter blocked sources
            if scope and results:
                results = [
                    r
                    for r in results
                    if not scope.is_blocked(r.get("url", r.get("source_url", "")))
                ]

            breaker.record_success()
            return results

        except Exception as exc:
            breaker.record_failure()
            logger.warning(
                "MCP source '%s' query failed: %s. Circuit breaker: %d/%d failures",
                name,
                exc,
                breaker.failure_count,
                CircuitBreaker.FAILURE_THRESHOLD,
            )
            return None

    async def _dispatch_query(self, name: str, params: dict) -> list[dict]:
        """Dispatch a query to the actual MCP server.

        This is the integration point where real MCP server calls will be made.
        Currently raises NotImplementedError -- will be wired to actual MCP
        servers when they're configured.

        Args:
            name: Source name.
            params: Query parameters.

        Returns:
            List of result dicts from the MCP server.

        Raises:
            NotImplementedError: MCP server integration not yet wired.
        """
        raise NotImplementedError(
            f"MCP server '{name}' not yet wired. "
            "Configure MCP server connections to enable live queries."
        )

    def get_available_sources(self) -> list[str]:
        """Return names of sources with closed circuit breakers."""
        return [
            name
            for name, breaker in self._breakers.items()
            if not breaker.is_open()
        ]

    def get_health_report(self) -> dict:
        """Get circuit breaker status per source.

        Returns:
            Dict mapping source name to status string.
        """
        report = {}
        for name, breaker in self._breakers.items():
            if breaker.is_open():
                status = f"OPEN (failures={breaker.failure_count})"
            elif breaker.failure_count > 0:
                status = f"DEGRADED (failures={breaker.failure_count})"
            else:
                status = "HEALTHY"
            report[name] = status
        return report
