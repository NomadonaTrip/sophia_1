"""Initial schema: all Phase 1 tables.

Revision ID: 001
Revises: None
Create Date: 2026-02-27

Creates: clients, voice_profiles, voice_materials, enrichment_log,
         audit_log, institutional_knowledge
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all Phase 1 tables."""

    # -- clients --
    op.create_table(
        "clients",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String, nullable=False, unique=True),
        sa.Column("industry", sa.String, nullable=False),
        sa.Column("business_description", sa.Text, nullable=True),
        sa.Column("geography_area", sa.String, nullable=True),
        sa.Column("geography_radius_km", sa.Integer, nullable=True),
        sa.Column("industry_vertical", sa.String, nullable=True),
        sa.Column("target_audience", sa.JSON, nullable=True),
        sa.Column("content_pillars", sa.JSON, nullable=True),
        sa.Column("posting_cadence", sa.JSON, nullable=True),
        sa.Column("platform_accounts", sa.JSON, nullable=True),
        sa.Column("guardrails", sa.JSON, nullable=True),
        sa.Column("brand_assets", sa.JSON, nullable=True),
        sa.Column("competitors", sa.JSON, nullable=True),
        sa.Column("market_scope", sa.JSON, nullable=True),
        sa.Column("is_archived", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("archived_at", sa.DateTime, nullable=True),
        sa.Column(
            "profile_completeness_pct", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column("is_mvp_ready", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("onboarding_state", sa.JSON, nullable=True),
        sa.Column("last_activity_at", sa.DateTime, nullable=True),
        sa.Column("last_action_summary", sa.String, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_clients_is_archived", "clients", ["is_archived"])

    # -- voice_profiles --
    op.create_table(
        "voice_profiles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "client_id",
            sa.Integer,
            sa.ForeignKey("clients.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("profile_data", sa.JSON, nullable=False),
        sa.Column(
            "overall_confidence_pct", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column("sample_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_calibrated_at", sa.DateTime, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # -- voice_materials --
    op.create_table(
        "voice_materials",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "client_id",
            sa.Integer,
            sa.ForeignKey("clients.id"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("source_url", sa.String, nullable=True),
        sa.Column("metadata", sa.JSON, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # -- enrichment_log --
    op.create_table(
        "enrichment_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "client_id",
            sa.Integer,
            sa.ForeignKey("clients.id"),
            nullable=False,
        ),
        sa.Column("field_name", sa.String, nullable=False),
        sa.Column("old_value", sa.Text, nullable=True),
        sa.Column("new_value", sa.Text, nullable=False),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("reason", sa.String, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # -- audit_log --
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "client_id",
            sa.Integer,
            sa.ForeignKey("clients.id"),
            nullable=True,
        ),
        sa.Column("action", sa.String, nullable=False),
        sa.Column("actor", sa.String, nullable=False, server_default="sophia"),
        sa.Column("details", sa.JSON, nullable=True),
        sa.Column("before_snapshot", sa.JSON, nullable=True),
        sa.Column("after_snapshot", sa.JSON, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_audit_log_client_action", "audit_log", ["client_id", "action"]
    )

    # -- institutional_knowledge --
    op.create_table(
        "institutional_knowledge",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("knowledge_type", sa.String, nullable=False),
        sa.Column("industry", sa.String, nullable=False),
        sa.Column("content", sa.JSON, nullable=False),
        sa.Column(
            "source_client_count", sa.Integer, nullable=False, server_default="1"
        ),
        sa.Column("confidence_score", sa.Float, nullable=False, server_default="0.5"),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    """Drop all Phase 1 tables in reverse dependency order."""
    op.drop_table("institutional_knowledge")
    op.drop_index("ix_audit_log_client_action", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_table("enrichment_log")
    op.drop_table("voice_materials")
    op.drop_table("voice_profiles")
    op.drop_index("ix_clients_is_archived", table_name="clients")
    op.drop_table("clients")
