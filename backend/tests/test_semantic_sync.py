"""Tests for write-through embedding sync from SQLite to LanceDB.

Uses in-memory/temp LanceDB for tests. Mocks the embedding functions
to return deterministic vectors.
"""

import asyncio
import logging
import sys
import types
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from sophia.semantic.embeddings import EMBEDDING_DIM
from sophia.semantic.index import reset_connection
from sophia.semantic.sync import sync_to_lance


@pytest.fixture
def lance_tmp(tmp_path):
    """Create a temporary LanceDB directory and return a connection."""
    import lancedb

    lance_path = str(tmp_path / "lance_test")
    db = lancedb.connect(lance_path)
    yield db
    reset_connection()


@pytest.fixture
def mock_embed():
    """Mock embed() to return a deterministic 1024-dim vector."""

    async def _embed(text):
        np.random.seed(hash(text) % (2**31))
        return np.random.randn(EMBEDDING_DIM).astype(np.float32).tolist()

    return _embed


@pytest.fixture
def mock_research_models():
    """Install mock research.models and intelligence.models in sys.modules.

    Provides stub model classes so reconcile_counts can import them.
    These stubs are replaced by real models in Task 2.
    """
    # Create mock model classes
    MockResearchFinding = type("ResearchFinding", (), {})
    MockCompetitorSnapshot = type("CompetitorSnapshot", (), {})
    MockPlatformIntelligence = type("PlatformIntelligence", (), {})
    MockIntelligenceEntry = type("IntelligenceEntry", (), {})

    # Ensure research.models module exists with the expected names
    research_models_mod = sys.modules.get("sophia.research.models")
    if research_models_mod is None:
        research_models_mod = types.ModuleType("sophia.research.models")
        sys.modules["sophia.research.models"] = research_models_mod

    if not hasattr(research_models_mod, "ResearchFinding"):
        research_models_mod.ResearchFinding = MockResearchFinding
    if not hasattr(research_models_mod, "CompetitorSnapshot"):
        research_models_mod.CompetitorSnapshot = MockCompetitorSnapshot
    if not hasattr(research_models_mod, "PlatformIntelligence"):
        research_models_mod.PlatformIntelligence = MockPlatformIntelligence

    # Ensure intelligence.models has IntelligenceEntry
    intel_models_mod = sys.modules.get("sophia.intelligence.models")
    had_ie = hasattr(intel_models_mod, "IntelligenceEntry") if intel_models_mod else False
    if intel_models_mod and not had_ie:
        intel_models_mod.IntelligenceEntry = MockIntelligenceEntry

    yield {
        "ResearchFinding": MockResearchFinding,
        "CompetitorSnapshot": MockCompetitorSnapshot,
        "PlatformIntelligence": MockPlatformIntelligence,
        "IntelligenceEntry": MockIntelligenceEntry,
    }

    # Cleanup
    if intel_models_mod and not had_ie:
        if hasattr(intel_models_mod, "IntelligenceEntry"):
            delattr(intel_models_mod, "IntelligenceEntry")


class TestSyncToLance:
    """Tests for write-through sync."""

    def test_sync_writes_to_lancedb(self, lance_tmp, mock_embed):
        """sync_to_lance creates a record in LanceDB."""
        with patch("sophia.semantic.sync.embed", side_effect=mock_embed):
            asyncio.get_event_loop().run_until_complete(
                sync_to_lance(
                    record_type="intelligence_entries",
                    record_id=1,
                    text="Business domain: Local bakery with strong community ties",
                    metadata={
                        "client_id": 10,
                        "domain": "business",
                        "created_at": "2026-02-27T00:00:00Z",
                    },
                    lance_db=lance_tmp,
                )
            )

        table = lance_tmp.open_table("intelligence_entries")
        assert table.count_rows() == 1

        df = table.to_pandas()
        assert df.iloc[0]["record_id"] == 1
        assert df.iloc[0]["record_type"] == "intelligence_entries"
        assert "bakery" in df.iloc[0]["text"]

    def test_sync_multiple_records(self, lance_tmp, mock_embed):
        """Multiple sync calls accumulate records in LanceDB."""
        with patch("sophia.semantic.sync.embed", side_effect=mock_embed):
            for i in range(3):
                asyncio.get_event_loop().run_until_complete(
                    sync_to_lance(
                        record_type="research_findings",
                        record_id=i + 1,
                        text=f"Finding {i}",
                        metadata={"client_id": 10, "domain": ""},
                        lance_db=lance_tmp,
                    )
                )

        table = lance_tmp.open_table("research_findings")
        assert table.count_rows() == 3

    def test_sync_failure_is_logged_not_raised(
        self, lance_tmp, mock_embed, caplog
    ):
        """If LanceDB sync fails, error is logged but not raised."""
        with patch(
            "sophia.semantic.sync.embed",
            side_effect=RuntimeError("GPU error"),
        ):
            with caplog.at_level(logging.ERROR):
                # Should NOT raise
                asyncio.get_event_loop().run_until_complete(
                    sync_to_lance(
                        record_type="intelligence_entries",
                        record_id=99,
                        text="This will fail",
                        metadata={"client_id": 1, "domain": "business"},
                        lance_db=lance_tmp,
                    )
                )

        assert "LANCE_SYNC_FAILED" in caplog.text

    def test_sync_stores_correct_metadata(self, lance_tmp, mock_embed):
        """Synced records contain correct client_id and domain metadata."""
        with patch("sophia.semantic.sync.embed", side_effect=mock_embed):
            asyncio.get_event_loop().run_until_complete(
                sync_to_lance(
                    record_type="intelligence_entries",
                    record_id=42,
                    text="Customer insight: Prefers evening browsing",
                    metadata={
                        "client_id": 7,
                        "domain": "customers",
                        "created_at": "2026-02-27T12:00:00Z",
                    },
                    lance_db=lance_tmp,
                )
            )

        table = lance_tmp.open_table("intelligence_entries")
        df = table.to_pandas()
        assert df.iloc[0]["client_id"] == 7
        assert df.iloc[0]["domain"] == "customers"
        assert df.iloc[0]["record_id"] == 42


class TestReconcileCounts:
    """Tests for SQLite vs LanceDB count reconciliation."""

    def test_reconcile_detects_mismatch(
        self, lance_tmp, mock_embed, mock_research_models
    ):
        """reconcile_counts reports drift when LanceDB has fewer rows than SQLite."""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.count.return_value = 5
        mock_session.query.return_value = mock_query

        # Add 2 rows to LanceDB for intelligence_entries
        with patch("sophia.semantic.sync.embed", side_effect=mock_embed):
            for i in range(2):
                asyncio.get_event_loop().run_until_complete(
                    sync_to_lance(
                        record_type="intelligence_entries",
                        record_id=i + 1,
                        text=f"Entry {i}",
                        metadata={"client_id": 1, "domain": "business"},
                        lance_db=lance_tmp,
                    )
                )

        with patch(
            "sophia.semantic.sync.get_lance_table",
        ) as mock_get_table:

            def table_side_effect(record_type, db=None):
                try:
                    return lance_tmp.open_table(record_type)
                except Exception:
                    mock_table = MagicMock()
                    mock_table.count_rows.return_value = 0
                    return mock_table

            mock_get_table.side_effect = table_side_effect

            from sophia.semantic.sync import reconcile_counts

            report = reconcile_counts(mock_session, lance_db=lance_tmp)

        assert report["intelligence_entries"]["sqlite"] == 5
        assert report["intelligence_entries"]["lance"] == 2
        assert report["intelligence_entries"]["drift"] == 3

    def test_reconcile_no_drift_when_equal(
        self, lance_tmp, mock_research_models
    ):
        """reconcile_counts reports zero drift when counts match."""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.count.return_value = 0
        mock_session.query.return_value = mock_query

        from sophia.semantic.sync import reconcile_counts

        report = reconcile_counts(mock_session, lance_db=lance_tmp)

        for table_name, counts in report.items():
            assert counts["drift"] == 0
