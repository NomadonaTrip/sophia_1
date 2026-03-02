"""Orchestrator models: cycle_runs, cycle_stages, specialist_agents,
chat_messages, auto_approval_configs, and content_drafts.cycle_id FK.

Revision ID: 002
Revises: 001
Create Date: 2026-03-02

Creates: cycle_runs, cycle_stages, specialist_agents, chat_messages,
         auto_approval_configs
Modifies: content_drafts (adds FK on cycle_id -> cycle_runs.id)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, Sequence[str], None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create orchestrator tables and add cycle_id FK."""

    # -- specialist_agents (must exist before cycle_runs references it) --
    op.create_table(
        "specialist_agents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "client_id",
            sa.Integer,
            sa.ForeignKey("clients.id"),
            nullable=False,
        ),
        sa.Column("specialty", sa.String(100), nullable=False),
        sa.Column("state_json", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("performance_metrics", sa.JSON, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("last_cycle_id", sa.Integer, nullable=True),
        sa.Column("total_cycles", sa.Integer, nullable=False, server_default="0"),
        sa.Column("approval_rate", sa.Float, nullable=False, server_default="0.0"),
        sa.Column(
            "false_positive_count", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column("false_positive_window_start", sa.DateTime, nullable=True),
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
        "ix_specialist_agents_client_id", "specialist_agents", ["client_id"]
    )

    # -- cycle_runs --
    op.create_table(
        "cycle_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "client_id",
            sa.Integer,
            sa.ForeignKey("clients.id"),
            nullable=False,
        ),
        sa.Column(
            "specialist_agent_id",
            sa.Integer,
            sa.ForeignKey("specialist_agents.id"),
            nullable=True,
        ),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="pending"
        ),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("drafts_generated", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "drafts_auto_approved", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column("drafts_flagged", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "research_findings_count",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "learnings_extracted", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column("observation_summary", sa.JSON, nullable=True),
        sa.Column("judgment_summary", sa.JSON, nullable=True),
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
    op.create_index("ix_cycle_runs_client_id", "cycle_runs", ["client_id"])
    op.create_index(
        "ix_cycle_runs_client_status", "cycle_runs", ["client_id", "status"]
    )

    # -- cycle_stages --
    op.create_table(
        "cycle_stages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "cycle_run_id",
            sa.Integer,
            sa.ForeignKey("cycle_runs.id"),
            nullable=False,
        ),
        sa.Column("stage_name", sa.String(30), nullable=False),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="pending"
        ),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("decision_trace", sa.JSON, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
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
        "ix_cycle_stages_cycle_run_id", "cycle_stages", ["cycle_run_id"]
    )

    # -- chat_messages --
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column(
            "client_context_id",
            sa.Integer,
            sa.ForeignKey("clients.id"),
            nullable=True,
        ),
        sa.Column("intent_type", sa.String(50), nullable=True),
        sa.Column("metadata_json", sa.JSON, nullable=True),
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

    # -- auto_approval_configs --
    op.create_table(
        "auto_approval_configs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "client_id",
            sa.Integer,
            sa.ForeignKey("clients.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="0"),
        sa.Column(
            "min_voice_confidence", sa.Float, nullable=False, server_default="0.75"
        ),
        sa.Column(
            "require_all_gates_pass",
            sa.Boolean,
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "max_content_risk",
            sa.String(20),
            nullable=False,
            server_default="safe",
        ),
        sa.Column(
            "min_historical_approval_rate",
            sa.Float,
            nullable=False,
            server_default="0.80",
        ),
        sa.Column(
            "burn_in_cycles", sa.Integer, nullable=False, server_default="15"
        ),
        sa.Column(
            "completed_cycles", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column(
            "editor_override_enabled",
            sa.Boolean,
            nullable=False,
            server_default="1",
        ),
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

    # -- Add FK from content_drafts.cycle_id -> cycle_runs.id --
    with op.batch_alter_table("content_drafts") as batch_op:
        batch_op.create_foreign_key(
            "fk_content_drafts_cycle_id",
            "cycle_runs",
            ["cycle_id"],
            ["id"],
        )


def downgrade() -> None:
    """Drop orchestrator tables and remove cycle_id FK."""

    # Remove FK from content_drafts first
    with op.batch_alter_table("content_drafts") as batch_op:
        batch_op.drop_constraint("fk_content_drafts_cycle_id", type_="foreignkey")

    # Drop tables in reverse dependency order
    op.drop_table("auto_approval_configs")
    op.drop_table("chat_messages")
    op.drop_index("ix_cycle_stages_cycle_run_id", table_name="cycle_stages")
    op.drop_table("cycle_stages")
    op.drop_index("ix_cycle_runs_client_status", table_name="cycle_runs")
    op.drop_index("ix_cycle_runs_client_id", table_name="cycle_runs")
    op.drop_table("cycle_runs")
    op.drop_index(
        "ix_specialist_agents_client_id", table_name="specialist_agents"
    )
    op.drop_table("specialist_agents")
