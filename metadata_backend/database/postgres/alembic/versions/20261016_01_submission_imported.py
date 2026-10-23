"""Add the imported flag and date columns to submissions.

A submission is imported when it was accessioned and ingested outside SD Submit.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261016_01"
down_revision = "20261008_01"
branch_labels = None
depends_on = None


_TABLE = "submissions"


def _columns() -> set[str]:
    """Return the columns of the submissions table, or nothing if the table does not exist."""

    inspector = sa.inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    columns = _columns()
    if not columns:
        return

    if "is_imported" not in columns:
        op.add_column(_TABLE, sa.Column("is_imported", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    if "imported" not in columns:
        op.add_column(_TABLE, sa.Column("imported", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    columns = _columns()
    for column in ("imported", "is_imported"):
        if column in columns:
            op.drop_column(_TABLE, column)
