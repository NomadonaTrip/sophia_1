"""SQLCipher engine factory with PRAGMA key injection.

Creates an encrypted SQLAlchemy engine using the pysqlcipher dialect.
Every connection automatically receives the encryption key and performance PRAGMAs.
"""

from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from sophia.config import get_settings


def create_db_engine() -> Engine:
    """Create a SQLCipher-encrypted SQLAlchemy engine.

    - Connection URL uses the pysqlcipher dialect for automatic PRAGMA key injection
    - Event listener sets WAL mode, foreign keys, and busy timeout on each connection
    - Creates parent directory of db_path if it doesn't exist
    """
    settings = get_settings()
    db_path = settings.db_path
    key = settings.db_encryption_key.get_secret_value()

    # Ensure the parent directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    url = f"sqlite+pysqlcipher://:{key}@/{db_path}"
    engine = create_engine(
        url,
        pool_pre_ping=True,
        echo=settings.debug,
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragmas(dbapi_connection, connection_record):
        """Set SQLite/SQLCipher PRAGMAs on every new connection."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    return engine


# Module-level singleton engine
engine = create_db_engine()

# Session factory bound to the engine
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """Context manager yielding a database session.

    Usage:
        with get_db() as db:
            clients = db.query(Client).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
