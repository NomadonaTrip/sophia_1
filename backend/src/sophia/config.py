"""Application configuration with SecretStr encryption key.

Loads settings from .env file with SOPHIA_ prefix.
Validates database path is on ext4 filesystem (not NTFS) to prevent WAL corruption in WSL2.
"""

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Sophia application settings.

    All settings are loaded from environment variables with SOPHIA_ prefix,
    or from a .env file in the working directory.
    """

    db_path: str = "/home/tayo/sophia/data/sophia.db"
    db_encryption_key: SecretStr
    backup_dir: str = "/home/tayo/sophia/data/backups"
    backup_retain_count: int = 7
    debug: bool = False
    operator_name: str = "Tayo"

    model_config = {
        "env_file": ".env",
        "env_prefix": "SOPHIA_",
    }

    @model_validator(mode="after")
    def validate_db_path_not_ntfs(self) -> "Settings":
        """Reject database paths on NTFS mounts to prevent WAL corruption."""
        if self.db_path.startswith("/mnt/"):
            raise ValueError(
                "Database path must be on ext4 filesystem, not NTFS (/mnt/). "
                "Use a path under /home/."
            )
        return self


def get_settings() -> Settings:
    """Create and return a Settings instance.

    Raises a clear error message if .env is missing or SOPHIA_DB_ENCRYPTION_KEY
    is not set.
    """
    try:
        return Settings()  # type: ignore[call-arg]
    except Exception as e:
        raise RuntimeError(
            f"Failed to load Sophia settings: {e}\n"
            "Ensure a .env file exists with at least SOPHIA_DB_ENCRYPTION_KEY set, "
            "or set the environment variable directly."
        ) from e
