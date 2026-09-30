"""Add dispatches table for tracking dispatched external service actions.

Revision ID: 20260923_01
Revises: 20260917_01
Create Date: 2026-09-23
"""

import sqlalchemy as sa
from alembic import op

revision = "20260923_01"
down_revision = "20260917_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dispatches",
        sa.Column(
            "submission_id",
            sa.String(128),
            sa.ForeignKey("submissions.submission_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("service", sa.String(32), primary_key=True),
        sa.Column("action", sa.String(64), primary_key=True),
        sa.Column("target", sa.String(128), primary_key=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_table("dispatches")
