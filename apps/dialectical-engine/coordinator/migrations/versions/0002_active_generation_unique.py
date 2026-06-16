"""enforce one active generation per node

Revision ID: 0002_active_generation_unique
Revises: 0001_initial
Create Date: 2026-05-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_active_generation_unique"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ux_generations_active_per_node",
        "generations",
        ["node_id"],
        unique=True,
        sqlite_where=sa.text("is_active = 1"),
    )


def downgrade() -> None:
    op.drop_index("ux_generations_active_per_node", table_name="generations")
