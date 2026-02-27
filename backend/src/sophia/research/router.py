"""FastAPI endpoints for research engine.

Provides endpoints to trigger research cycles, query findings, retrieve
daily digests, and check MCP source health.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from sophia.research.schemas import (
    FindingResponse,
    ResearchDigest,
)
from sophia.research.service import (
    generate_daily_digest,
    get_findings_for_content,
    run_research_cycle,
)
from sophia.research.sources import MCPSourceRegistry

router = APIRouter(prefix="/api/research", tags=["research"])

# Module-level source registry (singleton for the app lifetime)
_source_registry: Optional[MCPSourceRegistry] = None


def get_source_registry() -> MCPSourceRegistry:
    """Get or create the MCP source registry singleton."""
    global _source_registry
    if _source_registry is None:
        _source_registry = MCPSourceRegistry()
    return _source_registry


def _get_db_session():
    """Get a database session.

    This is a placeholder that will be replaced with proper dependency
    injection when the FastAPI app is assembled. For now, raises an
    error to make the dependency explicit.
    """
    raise NotImplementedError(
        "Database session dependency not configured. "
        "Wire get_db_session() when assembling the FastAPI app."
    )


@router.post("/{client_id}/cycle", response_model=ResearchDigest)
async def trigger_research_cycle(
    client_id: int,
    db=Depends(_get_db_session),
    registry: MCPSourceRegistry = Depends(get_source_registry),
) -> ResearchDigest:
    """Trigger a research cycle for a specific client.

    Executes the full daily research cycle: queries MCP sources,
    creates findings, syncs to LanceDB, and returns the digest.
    """
    try:
        digest = await run_research_cycle(
            db=db,
            client_id=client_id,
            source_registry=registry,
        )
        return digest
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Research cycle failed: {exc}",
        ) from exc


@router.get("/{client_id}/findings", response_model=list[FindingResponse])
async def get_findings(
    client_id: int,
    finding_type: Optional[str] = Query(None, description="Filter by finding type"),
    min_relevance: float = Query(0.0, ge=0.0, le=1.0, description="Minimum relevance score"),
    limit: int = Query(20, ge=1, le=100, description="Maximum results"),
    db=Depends(_get_db_session),
) -> list[FindingResponse]:
    """Get current research findings for a client.

    Returns findings filtered by type and relevance, sorted by
    relevance*confidence descending.
    """
    findings = get_findings_for_content(
        db=db,
        client_id=client_id,
        limit=limit,
        finding_type=finding_type,
        min_relevance=min_relevance,
    )
    return [
        FindingResponse(
            id=f.id,
            client_id=f.client_id,
            finding_type=f.finding_type.value if hasattr(f.finding_type, "value") else str(f.finding_type),
            topic=f.topic,
            summary=f.summary,
            content_angles=f.content_angles or [],
            source_url=f.source_url,
            source_name=f.source_name,
            relevance_score=f.relevance_score_val,
            confidence=f.confidence,
            is_time_sensitive=bool(f.is_time_sensitive),
            created_at=f.created_at,
            expires_at=f.expires_at,
        )
        for f in findings
    ]


@router.get("/{client_id}/digest", response_model=ResearchDigest)
async def get_digest(
    client_id: int,
    db=Depends(_get_db_session),
    registry: MCPSourceRegistry = Depends(get_source_registry),
) -> ResearchDigest:
    """Get the latest daily digest for a client.

    Assembles findings grouped by type with freshness metrics
    and source health status.
    """
    return generate_daily_digest(
        db=db,
        client_id=client_id,
        source_registry=registry,
    )


@router.get("/health")
async def get_health(
    registry: MCPSourceRegistry = Depends(get_source_registry),
) -> dict:
    """Get MCP source health report.

    Returns circuit breaker status for each registered source.
    """
    return {
        "sources": registry.get_health_report(),
        "available": registry.get_available_sources(),
    }
