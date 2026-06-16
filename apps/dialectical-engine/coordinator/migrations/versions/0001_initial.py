"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=120), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "debates",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("root_node_id", sa.String(length=36), nullable=True),
        sa.Column("synthesis_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_debates_status", "debates", ["status"])
    op.create_index("ix_debates_created_at", "debates", ["created_at"])
    op.create_table(
        "workers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False, unique=True),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("current_job_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_workers_last_seen", "workers", ["last_seen"])
    op.create_index("ix_workers_status", "workers", ["status"])
    op.create_table(
        "nodes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("debate_id", sa.String(length=36), sa.ForeignKey("debates.id"), nullable=False),
        sa.Column("parent_id", sa.String(length=36), sa.ForeignKey("nodes.id"), nullable=True),
        sa.Column("node_type", sa.String(length=16), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("active_generation_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("materialized_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_nodes_debate_id", "nodes", ["debate_id"])
    op.create_index("ix_nodes_parent_id", "nodes", ["parent_id"])
    op.create_index("ix_nodes_node_type", "nodes", ["node_type"])
    op.create_index("ix_nodes_depth", "nodes", ["depth"])
    op.create_index("ix_nodes_status", "nodes", ["status"])
    op.create_table(
        "generations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("node_id", sa.String(length=36), sa.ForeignKey("nodes.id"), nullable=False),
        sa.Column("model_id", sa.String(length=120), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("argument", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.String(length=40), nullable=False),
        sa.Column("prompt_rendered", sa.Text(), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("worker_id", sa.String(length=36), sa.ForeignKey("workers.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_generations_node_id", "generations", ["node_id"])
    op.create_index("ix_generations_model_id", "generations", ["model_id"])
    op.create_index("ix_generations_role", "generations", ["role"])
    op.create_index("ix_generations_is_active", "generations", ["is_active"])
    op.create_index("ix_generations_worker_id", "generations", ["worker_id"])
    op.create_table(
        "syntheses",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("debate_id", sa.String(length=36), sa.ForeignKey("debates.id"), nullable=False),
        sa.Column("strongest_pro", sa.Text(), nullable=False),
        sa.Column("strongest_con", sa.Text(), nullable=False),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column("model_id", sa.String(length=120), nullable=False),
        sa.Column("worker_id", sa.String(length=36), sa.ForeignKey("workers.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_syntheses_debate_id", "syntheses", ["debate_id"])
    op.create_index("ix_syntheses_model_id", "syntheses", ["model_id"])
    op.create_index("ix_syntheses_worker_id", "syntheses", ["worker_id"])
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("node_id", sa.String(length=36), sa.ForeignKey("nodes.id"), nullable=True),
        sa.Column("debate_id", sa.String(length=36), sa.ForeignKey("debates.id"), nullable=False),
        sa.Column("job_type", sa.String(length=24), nullable=False),
        sa.Column("required_role", sa.String(length=32), nullable=False),
        sa.Column("required_model", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("worker_id", sa.String(length=36), sa.ForeignKey("workers.id"), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=36), nullable=False, unique=True),
        sa.Column("stream_buffer", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_jobs_node_id", "jobs", ["node_id"])
    op.create_index("ix_jobs_debate_id", "jobs", ["debate_id"])
    op.create_index("ix_jobs_job_type", "jobs", ["job_type"])
    op.create_index("ix_jobs_required_role", "jobs", ["required_role"])
    op.create_index("ix_jobs_required_model", "jobs", ["required_model"])
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_worker_id", "jobs", ["worker_id"])
    op.create_index("ix_jobs_deadline", "jobs", ["deadline"])


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_table("syntheses")
    op.drop_table("generations")
    op.drop_table("nodes")
    op.drop_table("workers")
    op.drop_table("debates")
    op.drop_table("settings")

