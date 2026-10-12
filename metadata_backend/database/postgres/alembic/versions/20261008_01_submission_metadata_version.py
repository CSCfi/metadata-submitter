"""Add the metadata standard version column to submissions.

The version is set when a submission is created and never changed. Only Bigpicture
submissions have one. The Bigpicture submissions created before this migration are all
version 2.0, as earlier releases supported no other version. Only an NBIS database has
Bigpicture submissions.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261008_01"
down_revision = "20260923_01"
branch_labels = None
depends_on = None


_TABLE = "submissions"
_COLUMN = "metadata_version"


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

    if _COLUMN not in columns:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(16), nullable=True))

    op.execute(sa.text(f"UPDATE {_TABLE} SET {_COLUMN} = '2.0' WHERE workflow = 'Bigpicture' AND {_COLUMN} IS NULL"))


def downgrade() -> None:
    if _COLUMN in _columns():
        op.drop_column(_TABLE, _COLUMN)
