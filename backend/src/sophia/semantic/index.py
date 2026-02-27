"""LanceDB table management and hybrid semantic+keyword search.

Provides singleton LanceDB connection, table creation with FTS index,
and hybrid search with RRF (Reciprocal Rank Fusion) reranking.

Tables are stored on ext4 filesystem at /home/tayo/sophia/data/lance
per architecture decision (not NTFS to avoid corruption).
"""

from __future__ import annotations

import logging
from typing import Any

import lancedb
import pandas as pd
import pyarrow as pa
from lancedb.rerankers import RRFReranker

logger = logging.getLogger(__name__)

# Default LanceDB storage path (ext4 filesystem)
_DEFAULT_LANCE_PATH = "/home/tayo/sophia/data/lance"

# Module-level singleton connection
_db: lancedb.DBConnection | None = None

# BGE-M3 dense embedding dimension
_EMBEDDING_DIM = 1024

# Table names for each record type
TABLE_NAMES = {
    "research_findings": "research_findings",
    "intelligence_entries": "intelligence_entries",
    "competitor_snapshots": "competitor_snapshots",
    "platform_intelligence": "platform_intelligence",
}

# Schema for LanceDB tables (all share the same structure)
_LANCE_SCHEMA = pa.schema(
    [
        pa.field("vector", pa.list_(pa.float32(), _EMBEDDING_DIM)),
        pa.field("record_id", pa.int64()),
        pa.field("record_type", pa.string()),
        pa.field("text", pa.string()),
        pa.field("client_id", pa.int64()),
        pa.field("domain", pa.string()),
        pa.field("created_at", pa.string()),
    ]
)


def get_lance_db(path: str | None = None) -> lancedb.DBConnection:
    """Get or create singleton LanceDB connection.

    Args:
        path: Override path for testing. Defaults to /home/tayo/sophia/data/lance.

    Returns:
        LanceDB connection instance.
    """
    global _db
    if _db is None or path is not None:
        lance_path = path or _DEFAULT_LANCE_PATH
        logger.info("Connecting to LanceDB at %s", lance_path)
        _db = lancedb.connect(lance_path)
    return _db


def reset_connection() -> None:
    """Reset the singleton connection (for testing)."""
    global _db
    _db = None


def create_table(name: str, db: lancedb.DBConnection | None = None) -> Any:
    """Create a LanceDB table with the standard schema and FTS index.

    Creates a full-text search index on the 'text' column via Tantivy
    for hybrid semantic+keyword search.

    Args:
        name: Table name (e.g., 'research_findings').
        db: Optional LanceDB connection override.

    Returns:
        LanceDB table object.
    """
    conn = db if db is not None else get_lance_db()
    table = conn.create_table(name, schema=_LANCE_SCHEMA, mode="overwrite")
    # FTS index cannot be created on empty table in some LanceDB versions,
    # so we defer FTS index creation to first write via _ensure_fts_index
    logger.info("Created LanceDB table '%s'", name)
    return table


def _ensure_fts_index(table: Any) -> None:
    """Create FTS index on 'text' column if not already present.

    Called after the first data is inserted into a table, since some
    LanceDB versions require data to exist before creating FTS index.
    """
    try:
        table.create_fts_index("text", replace=True)
    except Exception as e:
        logger.warning("FTS index creation skipped: %s", e)


def get_lance_table(
    record_type: str, db: lancedb.DBConnection | None = None
) -> Any:
    """Get LanceDB table for a record type, creating if not exists.

    Args:
        record_type: One of 'research_findings', 'intelligence_entries',
            'competitor_snapshots', 'platform_intelligence'.
        db: Optional LanceDB connection override.

    Returns:
        LanceDB table object.
    """
    conn = db if db is not None else get_lance_db()
    table_name = TABLE_NAMES.get(record_type, record_type)

    try:
        return conn.open_table(table_name)
    except Exception:
        logger.info("Table '%s' not found, creating...", table_name)
        return create_table(table_name, db=conn)


def hybrid_search(
    table: Any,
    query_text: str,
    query_vector: list[float],
    limit: int = 10,
    filters: dict | None = None,
) -> pd.DataFrame:
    """Hybrid semantic + keyword search with RRF reranking.

    Combines vector similarity search with full-text keyword search
    using Reciprocal Rank Fusion for result merging.

    Args:
        table: LanceDB table to search.
        query_text: Text query for keyword search.
        query_vector: Embedding vector for semantic search.
        limit: Maximum number of results to return.
        filters: Optional column filters (e.g., {'client_id': 5}).

    Returns:
        DataFrame with columns: record_id, record_type, text, score, metadata.
    """
    reranker = RRFReranker()

    try:
        search = table.search(query_type="hybrid")
        search = search.vector(query_vector).text(query_text)
        search = search.rerank(reranker).limit(limit)

        if filters:
            filter_clauses = []
            for key, value in filters.items():
                if isinstance(value, str):
                    filter_clauses.append(f"{key} = '{value}'")
                else:
                    filter_clauses.append(f"{key} = {value}")
            if filter_clauses:
                search = search.where(" AND ".join(filter_clauses))

        results = search.to_pandas()
        return results
    except Exception as e:
        logger.warning("Hybrid search failed (table may be empty): %s", e)
        return pd.DataFrame(
            columns=[
                "vector",
                "record_id",
                "record_type",
                "text",
                "client_id",
                "domain",
                "created_at",
                "_relevance_score",
            ]
        )
