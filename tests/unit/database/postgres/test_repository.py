"""Test the database repository functions."""

import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory

from metadata_backend.database.postgres.models import Base
from metadata_backend.database.postgres.repository import (
    _ALEMBIC_DIR,
    create_engine,
    get_sqllite_db_url,
    migrate_schema,
)


def _head() -> str:
    config = Config()
    config.set_main_option("script_location", str(_ALEMBIC_DIR))
    head = ScriptDirectory.from_config(config).get_current_head()
    assert head is not None
    return head


def _tables(path) -> set[str]:
    engine = sa.create_engine(f"sqlite:///{path}")
    try:
        with engine.connect() as connection:
            return set(sa.inspect(connection).get_table_names())
    finally:
        engine.dispose()


def _version(path) -> str:
    engine = sa.create_engine(f"sqlite:///{path}")
    try:
        with engine.connect() as connection:
            return connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    finally:
        engine.dispose()


async def test_create_engine_no_tables(monkeypatch, tmp_path):
    """Test that a database without tables is created from the models and stamped instead of migrated."""
    path = tmp_path / "new.db"
    monkeypatch.setenv("DATABASE_URL", get_sqllite_db_url(str(path)))

    migrate_schema()
    assert _tables(path) == set()

    engine = await create_engine()
    await engine.dispose()
    assert _tables(path) == set(Base.metadata.tables) | {"alembic_version"}
    assert _version(path) == _head()

    # The next start has nothing to migrate.
    migrate_schema()
    assert _version(path) == _head()


async def test_create_engine_other_tables(monkeypatch, tmp_path):
    """Test that the tables are created in a database that has only tables not in the models."""
    path = tmp_path / "other.db"
    monkeypatch.setenv("DATABASE_URL", get_sqllite_db_url(str(path)))

    engine = sa.create_engine(f"sqlite:///{path}")
    try:
        with engine.begin() as connection:
            connection.execute(sa.text("CREATE TABLE other (id INTEGER PRIMARY KEY)"))
    finally:
        engine.dispose()

    migrate_schema()
    assert _tables(path) == {"other"}

    engine = await create_engine()
    await engine.dispose()
    assert _tables(path) == set(Base.metadata.tables) | {"alembic_version", "other"}
    assert _version(path) == _head()


async def test_test_create_engine_existing_tables(monkeypatch, tmp_path):
    """Test that no tables are created in a database that already has at least one of the tables."""
    path = tmp_path / "existing.db"
    monkeypatch.setenv("DATABASE_URL", get_sqllite_db_url(str(path)))

    engine = sa.create_engine(f"sqlite:///{path}")
    try:
        Base.metadata.tables["submissions"].create(engine)
    finally:
        engine.dispose()

    engine = await create_engine()
    await engine.dispose()
    assert _tables(path) == {"submissions"}
