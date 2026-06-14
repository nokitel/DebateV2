"""add dialectical v2 artifacts

Revision ID: 0003_dialectical_v2_artifacts
Revises: 0002_active_generation_unique
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_dialectical_v2_artifacts"
down_revision = "0002_active_generation_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("syntheses", sa.Column("upstream_agent_output_ids", sa.JSON(), nullable=True))
    op.add_column("syntheses", sa.Column("analyzer_findings", sa.JSON(), nullable=True))
    op.add_column("syntheses", sa.Column("provenance", sa.JSON(), nullable=True))

    op.create_table(
        "debate_branches",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("debate_id", sa.String(length=36), sa.ForeignKey("debates.id"), nullable=False),
        sa.Column("parent_branch_id", sa.String(length=36), sa.ForeignKey("debate_branches.id"), nullable=True),
        sa.Column("root_node_id", sa.String(length=36), sa.ForeignKey("nodes.id"), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_debate_branches_debate_id", "debate_branches", ["debate_id"])
    op.create_index("ix_debate_branches_parent_branch_id", "debate_branches", ["parent_branch_id"])
    op.create_index("ix_debate_branches_status", "debate_branches", ["status"])

    op.create_table(
        "skills",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("reuse_count", sa.Integer(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_skills_status", "skills", ["status"])

    op.create_table(
        "agents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("reuse_count", sa.Integer(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agents_status", "agents", ["status"])

    op.create_table(
        "analyzer_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("debate_id", sa.String(length=36), sa.ForeignKey("debates.id"), nullable=False),
        sa.Column("branch_id", sa.String(length=36), sa.ForeignKey("debate_branches.id"), nullable=False),
        sa.Column("analyzer_type", sa.String(length=80), nullable=False),
        sa.Column("output", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_analyzer_runs_debate_id", "analyzer_runs", ["debate_id"])
    op.create_index("ix_analyzer_runs_branch_id", "analyzer_runs", ["branch_id"])
    op.create_index("ix_analyzer_runs_analyzer_type", "analyzer_runs", ["analyzer_type"])
    op.create_index("ix_analyzer_runs_status", "analyzer_runs", ["status"])

    op.create_table(
        "capability_matches",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("debate_id", sa.String(length=36), sa.ForeignKey("debates.id"), nullable=False),
        sa.Column("branch_id", sa.String(length=36), sa.ForeignKey("debate_branches.id"), nullable=False),
        sa.Column("capability_kind", sa.String(length=16), nullable=False),
        sa.Column("capability_id", sa.String(length=36), nullable=False),
        sa.Column("selection_reason", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_capability_matches_debate_id", "capability_matches", ["debate_id"])
    op.create_index("ix_capability_matches_branch_id", "capability_matches", ["branch_id"])
    op.create_index("ix_capability_matches_capability_kind", "capability_matches", ["capability_kind"])
    op.create_index("ix_capability_matches_capability_id", "capability_matches", ["capability_id"])
    op.create_index("ix_capability_matches_selection_reason", "capability_matches", ["selection_reason"])

    op.create_table(
        "agent_outputs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("debate_id", sa.String(length=36), sa.ForeignKey("debates.id"), nullable=False),
        sa.Column("branch_id", sa.String(length=36), sa.ForeignKey("debate_branches.id"), nullable=False),
        sa.Column("skill_id", sa.String(length=36), sa.ForeignKey("skills.id"), nullable=True),
        sa.Column("agent_id", sa.String(length=36), sa.ForeignKey("agents.id"), nullable=True),
        sa.Column("agent_definition_id", sa.String(length=36), sa.ForeignKey("agents.id"), nullable=True),
        sa.Column("selected_skill_ids", sa.JSON(), nullable=False),
        sa.Column("role", sa.String(length=120), nullable=False),
        sa.Column("lens", sa.String(length=120), nullable=False),
        sa.Column("prompt_input", sa.JSON(), nullable=False),
        sa.Column("output", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("job_id", sa.String(length=36), sa.ForeignKey("jobs.id"), nullable=True),
        sa.Column("worker_id", sa.String(length=36), sa.ForeignKey("workers.id"), nullable=True),
        sa.Column("model_id", sa.String(length=120), nullable=True),
        sa.Column("analyzer_run_ids", sa.JSON(), nullable=False),
        sa.Column("pros", sa.JSON(), nullable=False),
        sa.Column("cons", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_outputs_debate_id", "agent_outputs", ["debate_id"])
    op.create_index("ix_agent_outputs_branch_id", "agent_outputs", ["branch_id"])
    op.create_index("ix_agent_outputs_skill_id", "agent_outputs", ["skill_id"])
    op.create_index("ix_agent_outputs_agent_id", "agent_outputs", ["agent_id"])
    op.create_index("ix_agent_outputs_agent_definition_id", "agent_outputs", ["agent_definition_id"])
    op.create_index("ix_agent_outputs_status", "agent_outputs", ["status"])
    op.create_index("ix_agent_outputs_job_id", "agent_outputs", ["job_id"])
    op.create_index("ix_agent_outputs_worker_id", "agent_outputs", ["worker_id"])
    op.create_index("ix_agent_outputs_model_id", "agent_outputs", ["model_id"])

    op.create_table(
        "provenance_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("debate_id", sa.String(length=36), sa.ForeignKey("debates.id"), nullable=False),
        sa.Column("branch_id", sa.String(length=36), sa.ForeignKey("debate_branches.id"), nullable=True),
        sa.Column("artifact_kind", sa.String(length=40), nullable=False),
        sa.Column("artifact_id", sa.String(length=36), nullable=False),
        sa.Column("model_id", sa.String(length=120), nullable=False),
        sa.Column("worker_id", sa.String(length=120), nullable=False),
        sa.Column("prompt_id", sa.String(length=120), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_provenance_records_debate_id", "provenance_records", ["debate_id"])
    op.create_index("ix_provenance_records_branch_id", "provenance_records", ["branch_id"])
    op.create_index("ix_provenance_records_artifact_kind", "provenance_records", ["artifact_kind"])
    op.create_index("ix_provenance_records_artifact_id", "provenance_records", ["artifact_id"])


def downgrade() -> None:
    op.drop_table("provenance_records")
    op.drop_table("agent_outputs")
    op.drop_table("capability_matches")
    op.drop_table("analyzer_runs")
    op.drop_table("agents")
    op.drop_table("skills")
    op.drop_table("debate_branches")
    op.drop_column("syntheses", "provenance")
    op.drop_column("syntheses", "analyzer_findings")
    op.drop_column("syntheses", "upstream_agent_output_ids")
