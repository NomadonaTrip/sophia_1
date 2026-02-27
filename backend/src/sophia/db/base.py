"""DeclarativeBase, TimestampMixin, and soft-delete mixin for all ORM models."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 declarative base for all Sophia models."""

    pass


class TimestampMixin:
    """Mixin providing created_at and updated_at timestamps.

    Uses server_default for initial values and onupdate for tracking modifications.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
