"""Alembic migration runner using the application's SQLCipher engine.

Uses the pre-configured engine from sophia.db.engine, which already handles
encryption key injection and PRAGMA configuration.
"""

from logging.config import fileConfig

from alembic import context

# Import all model modules to register them with Base.metadata
import sophia.intelligence.models  # noqa: F401
import sophia.institutional.models  # noqa: F401
from sophia.db.base import Base
from sophia.db.engine import engine

# Alembic Config object
config = context.config

# Set up Python logging from the ini file
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate support
target_metadata = Base.metadata


def run_migrations_online() -> None:
    """Run migrations using the application's SQLCipher engine."""
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
