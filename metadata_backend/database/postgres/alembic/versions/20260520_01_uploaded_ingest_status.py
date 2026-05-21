"""Add uploaded status to files ingest-status constraint.

Revision ID: 20260520_01
Revises:
Create Date: 2026-05-20
"""

from alembic import op

revision = "20260520_01"
down_revision = None
branch_labels = None
depends_on = None


_NEW_CONSTRAINT = "ingest_status IN ('submitted', 'uploaded', 'verified', 'ready', 'error')"
_OLD_CONSTRAINT = "ingest_status IN ('submitted', 'verified', 'ready', 'error')"


def _table_exists_clause() -> str:
    return (
        "EXISTS ("
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = current_schema() AND table_name = 'files'"
        ")"
    )


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF {_table_exists_clause()} THEN
                ALTER TABLE files DROP CONSTRAINT IF EXISTS ck_ingest_status;
                ALTER TABLE files ADD CONSTRAINT ck_ingest_status CHECK ({_NEW_CONSTRAINT});
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF {_table_exists_clause()} THEN
                ALTER TABLE files DROP CONSTRAINT IF EXISTS ck_ingest_status;
                ALTER TABLE files ADD CONSTRAINT ck_ingest_status CHECK ({_OLD_CONSTRAINT});
            END IF;
        END
        $$;
        """
    )
