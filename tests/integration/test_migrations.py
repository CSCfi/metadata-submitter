"""Test the Alembic migrations against a temporary PostgreSQL database."""

import asyncio
import uuid

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext

from metadata_backend.database.postgres.models import Base
from metadata_backend.database.postgres.repository import _alembic_config, create_engine

from .conf import nbis_database_url

pytestmark = pytest.mark.skipif(nbis_database_url is None, reason="Needs the NBIS database server.")

_XML = "<DATASET><TITLE>Migrated</TITLE></DATASET>"


@pytest.fixture
def database_url(monkeypatch):
    """A new database on the NBIS database server, removed after the test."""
    server = sa.make_url(nbis_database_url).set(drivername="postgresql+psycopg", database="postgres")
    name = f"migrations_{uuid.uuid4().hex}"

    admin = sa.create_engine(server, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(sa.text(f"CREATE DATABASE {name}"))
    try:
        url = sa.make_url(nbis_database_url).set(database=name)
        monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
        # Keep the metadata objects unencrypted, so that they can be read back directly.
        monkeypatch.delenv("OPENBAO_URL", raising=False)
        yield url.set(drivername="postgresql+psycopg")
    finally:
        with admin.connect() as connection:
            connection.execute(sa.text(f"DROP DATABASE {name} WITH (FORCE)"))
        admin.dispose()


async def _create_schema() -> None:
    """Create the schema as the server does when it starts."""
    engine = await create_engine()
    await engine.dispose()


def _version(connection: sa.Connection) -> str | None:
    return MigrationContext.configure(connection).get_current_revision()


def test_downgrade_and_upgrade(database_url):
    """Test that every migration downgrades to the bottom and upgrades back to the models' schema."""

    # A new database is created from the models and stamped with the latest revision.
    asyncio.run(_create_schema())

    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as connection:
            head = _version(connection)
            assert head is not None
            connection.execute(
                sa.text(
                    "INSERT INTO submissions (submission_id, name, project_id, workflow, metadata_version, document) "
                    "VALUES ('bp', 'bp', 'project', 'Bigpicture', '2.0', '{}')"
                )
            )
            connection.execute(
                sa.text(
                    "INSERT INTO objects (object_id, object_type, submission_id, project_id, object) "
                    "VALUES ('object', 'dataset', 'bp', 'project', :object)"
                ),
                {"object": _XML.encode("utf-8")},
            )

        command.downgrade(_alembic_config(), "base")
        with engine.connect() as connection:
            assert _version(connection) is None

            # The initial schema before migrations.
            inspector = sa.inspect(connection)
            assert "dispatches" not in inspector.get_table_names()
            assert "metadata_version" not in {column["name"] for column in inspector.get_columns("submissions")}
            assert {column["name"] for column in inspector.get_columns("objects")} >= {"xml_document", "document"}

        command.upgrade(_alembic_config(), "head")
        with engine.connect() as connection:
            assert _version(connection) == head

            # The schema after migrations.
            inspector = sa.inspect(connection)
            assert "dispatches" in inspector.get_table_names()
            assert "metadata_version" in {column["name"] for column in inspector.get_columns("submissions")}
            objects_columns = {column["name"] for column in inspector.get_columns("objects")}
            assert "object" in objects_columns
            assert objects_columns.isdisjoint({"xml_document", "document"})

            # The schema matches the models again.
            assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []

            # The data survives the migrations.
            assert connection.execute(sa.text("SELECT metadata_version FROM submissions")).scalar_one() == "2.0"
            assert connection.execute(sa.text("SELECT object FROM objects")).scalar_one() == _XML.encode("utf-8")
    finally:
        engine.dispose()
