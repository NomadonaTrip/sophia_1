"""Test fixtures for Sophia integration tests.

Uses SQLCipher-encrypted temp database to validate operations work
with encryption enabled, matching the production engine pattern.
"""

import os
import tempfile

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from sophia.db.base import Base
from sophia.intelligence.models import (  # noqa: F401 -- ensure models registered
    AuditLog,
    Client,
    EnrichmentLog,
    IntelligenceEntry,
    IntelligenceInstitutionalKnowledge,
    VoiceMaterial,
    VoiceProfile,
)
from sophia.institutional.models import InstitutionalKnowledge  # noqa: F401
from sophia.research.models import (  # noqa: F401 -- ensure models registered
    Competitor,
    CompetitorSnapshot,
    PlatformIntelligence,
    ResearchFinding,
)
from sophia.content.models import (  # noqa: F401 -- ensure models registered
    CalibrationRound,
    CalibrationSession,
    ContentDraft,
    EvergreenEntry,
    FormatPerformance,
    RegenerationLog,
)
from sophia.intelligence.schemas import ClientCreate
from sophia.intelligence.service import ClientService


TEST_ENCRYPTION_KEY = "test_encryption_key_sophia_ci_12345"


@pytest.fixture(scope="session")
def test_engine():
    """Create a SQLCipher-encrypted test database engine.

    Uses a temp file on ext4 at /tmp to match production constraints.
    Creates all tables via Base.metadata.create_all.
    """
    tmpfile = tempfile.NamedTemporaryFile(
        suffix=".db", dir="/tmp", delete=False, prefix="sophia_test_"
    )
    db_path = tmpfile.name
    tmpfile.close()

    url = f"sqlite+pysqlcipher://:{TEST_ENCRYPTION_KEY}@/{db_path}"
    engine = create_engine(url, echo=False)

    @event.listens_for(engine, "connect")
    def set_pragmas(dbapi_conn, conn_rec):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    # Create all tables
    Base.metadata.create_all(engine)

    yield engine

    # Teardown: drop tables, remove temp file
    Base.metadata.drop_all(engine)
    engine.dispose()
    try:
        os.unlink(db_path)
        # Also clean up WAL and SHM files
        for ext in ("-wal", "-shm"):
            wal_path = db_path + ext
            if os.path.exists(wal_path):
                os.unlink(wal_path)
    except OSError:
        pass


@pytest.fixture
def db_session(test_engine):
    """Create a database session for each test.

    Rolls back all changes after each test to maintain isolation.
    """
    connection = test_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def sample_client(db_session):
    """Create a test client: Orban Forest, Marketing Agency."""
    data = ClientCreate(name="Orban Forest", industry="Marketing Agency")
    return ClientService.create_client(db_session, data)


@pytest.fixture
def sample_client_2(db_session):
    """Create a second test client: Shane's Bakery, Food & Beverage."""
    data = ClientCreate(name="Shane's Bakery", industry="Food & Beverage")
    return ClientService.create_client(db_session, data)
