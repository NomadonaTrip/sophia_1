"""Write-through embedding sync from SQLite to LanceDB.

Every SQLite write for research findings and intelligence entries triggers
a write-through embedding to LanceDB. The sync happens AFTER the SQLite
commit succeeds -- never during an open transaction.

If LanceDB sync fails, the error is logged prominently but NOT raised,
ensuring SQLite data is safe. The batch_reindex function provides recovery.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from sophia.semantic.embeddings import embed, embed_batch
from sophia.semantic.index import _ensure_fts_index, get_lance_table

logger = logging.getLogger(__name__)


async def sync_to_lance(
    record_type: str,
    record_id: int,
    text: str,
    metadata: dict,
    lance_db=None,
) -> None:
    """Embed text and upsert into LanceDB after SQLite commit.

    Called AFTER successful SQLite commit. If LanceDB sync fails, logs the
    error prominently but does not raise -- SQLite data is the source of truth.

    Args:
        record_type: Type of record ('research_findings', 'intelligence_entries', etc.).
        record_id: SQLite primary key of the record.
        text: Text content to embed.
        metadata: Additional metadata dict with keys like client_id, domain, created_at.
        lance_db: Optional LanceDB connection override (for testing).
    """
    try:
        vector = await embed(text)
        table = get_lance_table(record_type, db=lance_db)

        row = {
            "vector": vector,
            "record_id": record_id,
            "record_type": record_type,
            "text": text,
            "client_id": metadata.get("client_id", 0),
            "domain": metadata.get("domain", ""),
            "created_at": metadata.get(
                "created_at", datetime.now(timezone.utc).isoformat()
            ),
        }

        table.add([row])
        _ensure_fts_index(table)

        logger.debug(
            "Synced %s record_id=%d to LanceDB",
            record_type,
            record_id,
        )
    except Exception:
        logger.exception(
            "LANCE_SYNC_FAILED: Failed to sync %s record_id=%d to LanceDB. "
            "SQLite data is safe. Run batch_reindex to recover.",
            record_type,
            record_id,
        )


def reconcile_counts(db: Session, lance_db=None) -> dict:
    """Compare SQLite record counts per type against LanceDB row counts.

    Returns a discrepancy report suitable for daily health checks.

    Args:
        db: SQLAlchemy session for querying SQLite.
        lance_db: Optional LanceDB connection override.

    Returns:
        Dict with per-table comparison: {table_name: {sqlite: N, lance: M, drift: K}}.
    """
    from sophia.intelligence.models import IntelligenceEntry
    from sophia.research.models import (
        CompetitorSnapshot,
        PlatformIntelligence,
        ResearchFinding,
    )

    model_map = {
        "research_findings": ResearchFinding,
        "intelligence_entries": IntelligenceEntry,
        "competitor_snapshots": CompetitorSnapshot,
        "platform_intelligence": PlatformIntelligence,
    }

    report: dict[str, dict] = {}

    for record_type, model in model_map.items():
        sqlite_count = db.query(model).count()

        try:
            table = get_lance_table(record_type, db=lance_db)
            lance_count = table.count_rows()
        except Exception:
            lance_count = 0

        drift = sqlite_count - lance_count
        report[record_type] = {
            "sqlite": sqlite_count,
            "lance": lance_count,
            "drift": drift,
        }

        if drift != 0:
            logger.warning(
                "LANCE_DRIFT: %s has %d SQLite rows but %d LanceDB rows (drift=%d)",
                record_type,
                sqlite_count,
                lance_count,
                drift,
            )

    return report


async def batch_reindex(
    db: Session,
    record_type: str,
    lance_db=None,
) -> int:
    """Full re-index from SQLite for recovery.

    Reads all records of the given type from SQLite, embeds them in batches
    via embed_batch(), and overwrites the LanceDB table.

    Args:
        db: SQLAlchemy session for querying SQLite.
        record_type: One of 'research_findings', 'intelligence_entries', etc.
        lance_db: Optional LanceDB connection override.

    Returns:
        Number of records re-indexed.
    """
    from sophia.intelligence.models import IntelligenceEntry
    from sophia.research.models import (
        CompetitorSnapshot,
        PlatformIntelligence,
        ResearchFinding,
    )

    model_map = {
        "research_findings": ResearchFinding,
        "intelligence_entries": IntelligenceEntry,
        "competitor_snapshots": CompetitorSnapshot,
        "platform_intelligence": PlatformIntelligence,
    }

    model = model_map.get(record_type)
    if model is None:
        raise ValueError(f"Unknown record type: {record_type}")

    records = db.query(model).all()
    if not records:
        logger.info("No %s records to reindex.", record_type)
        return 0

    logger.info("Reindexing %d %s records...", len(records), record_type)

    # Extract text for each record
    texts = []
    record_data = []
    for record in records:
        text = _extract_text(record, record_type)
        texts.append(text)
        record_data.append(
            {
                "record_id": record.id,
                "record_type": record_type,
                "text": text,
                "client_id": record.client_id,
                "domain": _extract_domain(record, record_type),
                "created_at": (
                    record.created_at.isoformat()
                    if record.created_at
                    else datetime.now(timezone.utc).isoformat()
                ),
            }
        )

    # Batch embed
    batch_size = 32
    all_vectors = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        vectors = await embed_batch(batch)
        all_vectors.extend(vectors)
        logger.info(
            "Embedded batch %d-%d of %d",
            i,
            min(i + batch_size, len(texts)),
            len(texts),
        )

    # Build rows and overwrite table
    rows = []
    for vec, data in zip(all_vectors, record_data):
        rows.append({"vector": vec, **data})

    from sophia.semantic.index import create_table

    table = create_table(record_type, db=lance_db)
    if rows:
        table.add(rows)
        _ensure_fts_index(table)

    logger.info("Reindexed %d %s records.", len(rows), record_type)
    return len(rows)


def _extract_text(record, record_type: str) -> str:
    """Extract searchable text from a SQLAlchemy record."""
    if record_type == "research_findings":
        return f"{record.topic}: {record.summary}"
    elif record_type == "intelligence_entries":
        return f"{record.domain.value if hasattr(record.domain, 'value') else record.domain}: {record.fact}"
    elif record_type == "competitor_snapshots":
        themes = record.top_content_themes or ""
        return f"Competitor snapshot: {themes}"
    elif record_type == "platform_intelligence":
        return f"{record.platform} {record.category}: {record.insight}"
    return str(record)


def _extract_domain(record, record_type: str) -> str:
    """Extract domain string from a record for LanceDB metadata."""
    if record_type == "intelligence_entries":
        return record.domain.value if hasattr(record.domain, "value") else str(record.domain)
    if record_type == "platform_intelligence":
        return record.platform
    return ""
