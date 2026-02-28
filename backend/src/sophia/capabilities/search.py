"""Capability search services for MCP Registry and GitHub.

Searches for MCP servers and GitHub repositories that may fill
identified capability gaps. Results are returned as lightweight
dataclasses for downstream evaluation.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredCapabilityData:
    """Lightweight data container for search results (not a DB model).

    Carries enough metadata for evaluation and deduplication before
    being persisted as a DiscoveredCapability ORM record.
    """

    name: str
    description: str
    url: str
    source: str  # "mcp_registry" or "github"
    version: Optional[str] = None
    stars: Optional[int] = None
    last_updated: Optional[datetime] = None


MCP_REGISTRY_URL = "https://registry.modelcontextprotocol.io/v0/servers"


async def search_mcp_registry(
    query: str, limit: int = 10
) -> list[DiscoveredCapabilityData]:
    """Search the MCP Registry API for servers matching a query.

    GET https://registry.modelcontextprotocol.io/v0/servers?search={query}&limit={limit}

    Returns parsed results as DiscoveredCapabilityData. Handles HTTP errors
    gracefully -- logs the error and returns an empty list.
    """
    results: list[DiscoveredCapabilityData] = []

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                MCP_REGISTRY_URL,
                params={"search": query, "limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()

            # The MCP Registry returns a list of server objects
            servers = data if isinstance(data, list) else data.get("servers", [])

            for server in servers[:limit]:
                name = server.get("name", "")
                description = server.get("description", "")
                # Repository URL may be in 'repository' or 'url' field
                url = (
                    server.get("repository", {}).get("url", "")
                    if isinstance(server.get("repository"), dict)
                    else server.get("repository", server.get("url", ""))
                )
                version = server.get("version", None)

                if name and url:
                    results.append(
                        DiscoveredCapabilityData(
                            name=name,
                            description=description or "No description available",
                            url=str(url),
                            source="mcp_registry",
                            version=version,
                            stars=None,
                            last_updated=None,
                        )
                    )

    except httpx.HTTPStatusError as e:
        logger.warning(
            "MCP Registry search failed with HTTP %s: %s",
            e.response.status_code,
            str(e),
        )
    except httpx.RequestError as e:
        logger.warning("MCP Registry search request failed: %s", str(e))
    except Exception as e:
        logger.warning("MCP Registry search unexpected error: %s", str(e))

    return results


def _get_github_client():
    """Create an authenticated GitHub client from settings.

    Lazy-imports PyGithub and settings to avoid slow NTFS imports.
    Returns None if no token is configured (falls back to unauthenticated).
    """
    try:
        from github import Github

        try:
            from sophia.config import get_settings

            settings = get_settings()
            token = getattr(settings, "github_token", "")
            if token:
                return Github(token)
        except Exception:
            pass

        # Unauthenticated fallback (60 req/hour)
        return Github()
    except ImportError:
        logger.warning("PyGithub not installed -- GitHub search unavailable")
        return None


async def search_github(
    query: str, limit: int = 10
) -> list[DiscoveredCapabilityData]:
    """Search GitHub repositories for MCP servers and tools.

    Uses PyGithub with authenticated token from settings for higher rate
    limits (5,000 req/hour vs 60 unauthenticated).

    Returns parsed results. Handles rate limit errors gracefully.
    """
    results: list[DiscoveredCapabilityData] = []

    def _search_sync() -> list[DiscoveredCapabilityData]:
        """Run synchronous PyGithub search in a thread."""
        inner_results: list[DiscoveredCapabilityData] = []

        g = _get_github_client()
        if g is None:
            return inner_results

        try:
            # Search for MCP servers and Claude Code skills
            search_query = f"mcp server {query}"
            repos = g.search_repositories(
                query=search_query, sort="stars", order="desc"
            )

            count = 0
            for repo in repos:
                if count >= limit:
                    break

                # Extract latest release tag if available
                version = None
                try:
                    latest = repo.get_latest_release()
                    version = latest.tag_name
                except Exception:
                    pass

                inner_results.append(
                    DiscoveredCapabilityData(
                        name=repo.full_name,
                        description=repo.description or "No description",
                        url=repo.html_url,
                        source="github",
                        version=version,
                        stars=repo.stargazers_count,
                        last_updated=repo.updated_at,
                    )
                )
                count += 1

        except Exception as e:
            error_str = str(e)
            if "403" in error_str or "rate limit" in error_str.lower():
                logger.warning(
                    "GitHub rate limit hit -- returning %d partial results",
                    len(inner_results),
                )
            else:
                logger.warning("GitHub search failed: %s", error_str)

        return inner_results

    # Run synchronous PyGithub in a thread to avoid blocking the event loop
    results = await asyncio.to_thread(_search_sync)
    return results


async def search_all_sources(
    query: str, limit_per_source: int = 10
) -> list[DiscoveredCapabilityData]:
    """Search MCP Registry and GitHub concurrently, deduplicate, and rank.

    Runs both search sources via asyncio.gather, deduplicates by URL,
    and sorts: MCP Registry results first, then by GitHub stars descending.
    """
    mcp_results, github_results = await asyncio.gather(
        search_mcp_registry(query, limit=limit_per_source),
        search_github(query, limit=limit_per_source),
        return_exceptions=True,
    )

    # Handle exceptions from gather
    if isinstance(mcp_results, BaseException):
        logger.warning("MCP Registry search raised: %s", mcp_results)
        mcp_results = []
    if isinstance(github_results, BaseException):
        logger.warning("GitHub search raised: %s", github_results)
        github_results = []

    # Combine all results
    all_results = list(mcp_results) + list(github_results)

    # Deduplicate by URL (case-insensitive)
    seen_urls: set[str] = set()
    unique_results: list[DiscoveredCapabilityData] = []
    for result in all_results:
        normalized_url = result.url.lower().rstrip("/")
        if normalized_url not in seen_urls:
            seen_urls.add(normalized_url)
            unique_results.append(result)

    # Sort: MCP Registry first, then by stars (descending, None last)
    def _sort_key(cap: DiscoveredCapabilityData) -> tuple:
        source_priority = 0 if cap.source == "mcp_registry" else 1
        star_score = -(cap.stars or 0)
        return (source_priority, star_score)

    unique_results.sort(key=_sort_key)

    return unique_results
