"""InstitutionalKnowledge ORM model for anonymized ICP data.

Stores industry-level patterns extracted from client data during archival.
Intentionally has no FK to clients table -- this enforces SAFE-01 data isolation.
"""

from typing import Optional

from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from sophia.db.base import Base, TimestampMixin


class InstitutionalKnowledge(TimestampMixin, Base):
    """Anonymized cross-client industry knowledge.

    No foreign key to clients -- this data is intentionally decoupled
    to maintain data isolation (SAFE-01). Knowledge is extracted during
    client archival and stored as anonymized industry patterns.
    """

    __tablename__ = "institutional_knowledge"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    knowledge_type: Mapped[str] = mapped_column(String, nullable=False)
    industry: Mapped[str] = mapped_column(String, nullable=False)

    from sqlalchemy import JSON

    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_client_count: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False
    )
    confidence_score: Mapped[float] = mapped_column(
        Float, default=0.5, nullable=False
    )
