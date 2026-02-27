"""Encrypted backup via ATTACH + sqlcipher_export.

Uses SQLCipher's native backup mechanism instead of the SQLite Online Backup API,
which has known issues with encrypted databases.
"""

from pathlib import Path

import structlog
from sqlalchemy import Engine, text

from sophia.exceptions import BackupError

logger = structlog.get_logger(__name__)


def create_encrypted_backup(
    engine: Engine,
    backup_dir: Path,
    encryption_key: str,
    retain_count: int = 7,
) -> Path:
    """Create an encrypted backup of the SQLCipher database.

    Uses ATTACH DATABASE + sqlcipher_export for safe encrypted backup.
    Rotates old backups, keeping only the most recent `retain_count` files.

    Args:
        engine: SQLAlchemy engine connected to the source database.
        backup_dir: Directory to store backup files.
        encryption_key: Encryption key for the backup database.
        retain_count: Number of backup files to retain (default: 7).

    Returns:
        Path to the newly created backup file.

    Raises:
        BackupError: If backup creation or rotation fails.
    """
    from datetime import datetime, timezone

    try:
        # Ensure backup directory exists
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"sophia_backup_{timestamp}.db"

        logger.info(
            "creating_encrypted_backup",
            backup_path=str(backup_path),
        )

        with engine.connect() as conn:
            # Use raw connection to execute SQLCipher-specific commands
            raw_conn = conn.connection.dbapi_connection
            cursor = raw_conn.cursor()
            cursor.execute(
                f"ATTACH DATABASE '{backup_path}' AS backup KEY '{encryption_key}'"
            )
            cursor.execute("SELECT sqlcipher_export('backup')")
            cursor.execute("DETACH DATABASE backup")
            cursor.close()

        logger.info(
            "backup_created",
            backup_path=str(backup_path),
            size_bytes=backup_path.stat().st_size,
        )

        # Rotate old backups
        backups = sorted(
            backup_dir.glob("sophia_backup_*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        removed_count = 0
        for old_backup in backups[retain_count:]:
            old_backup.unlink()
            removed_count += 1

        if removed_count > 0:
            logger.info(
                "backups_rotated",
                removed=removed_count,
                retained=retain_count,
            )

        return backup_path

    except BackupError:
        raise
    except Exception as e:
        raise BackupError(
            message="Failed to create encrypted backup",
            detail=str(e),
            suggestion="Check backup directory permissions and disk space",
        ) from e
