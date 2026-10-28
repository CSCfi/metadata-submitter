"""Test the database repository functions."""

from unittest.mock import AsyncMock, MagicMock

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory

from metadata_backend.api.exceptions import SystemException
from metadata_backend.api.models.models import Registration
from metadata_backend.database.postgres.models import Base, SubmissionEntity
from metadata_backend.database.postgres.repositories.registration import RegistrationRepository
from metadata_backend.database.postgres.repositories.submission import SubmissionRepository
from metadata_backend.database.postgres.repository import (
    _ALEMBIC_DIR,
    COMMITTED_SESSION_LOCK_TIMEOUT,
    _session_context,
    allow_no_committed_session,
    committed_session,
    create_engine,
    create_session_factory,
    get_sqllite_db_url,
    migrate_schema,
    session_factory_context,
)
from metadata_backend.database.postgres.services.registration import RegistrationService
from tests.unit.database.postgres.helpers import create_submission_entity


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


async def test_committed_session(monkeypatch, tmp_path):
    """Test that the committed session is kept when the outer transaction is rolled back."""
    monkeypatch.setenv("DATABASE_URL", get_sqllite_db_url(str(tmp_path / "committed.db")))
    engine = await create_engine()
    session_factory = create_session_factory(engine)
    token = session_factory_context.set(session_factory)
    try:
        async with session_factory() as outer_session:
            await outer_session.begin()
            async with committed_session():
                submission_id = await SubmissionRepository().add_submission(create_submission_entity())
            await outer_session.rollback()

        async with session_factory() as new_session:
            assert await new_session.get(SubmissionEntity, submission_id) is not None
    finally:
        session_factory_context.reset(token)
        await engine.dispose()


async def test_allow_no_committed_session(session):

    # The session fixture permits committed_session() calls.
    async with committed_session():
        submission_id = await SubmissionRepository().add_submission(create_submission_entity())
    assert await session.get(SubmissionEntity, submission_id) is not None

    token = allow_no_committed_session.set(False)
    try:
        with pytest.raises(SystemException, match="No session factory has been defined"):
            async with committed_session():
                pass
    finally:
        allow_no_committed_session.reset(token)


@pytest.mark.parametrize("dialect, lock_timeout", [("postgresql", True), ("sqlite", False)])
async def test_committed_session_lock_timeout(dialect, lock_timeout):
    """Test that a committed transaction in PostgreSQL waits for a row lock only until the lock timeout."""
    committed = MagicMock()
    committed.__aenter__.return_value = committed
    committed.begin.return_value = MagicMock()
    committed.bind.dialect.name = dialect
    committed.execute = AsyncMock()
    session_factory = MagicMock(return_value=committed)

    token = session_factory_context.set(session_factory)
    try:
        async with committed_session():
            pass
    finally:
        session_factory_context.reset(token)

    statements = [str(call.args[0]) for call in committed.execute.await_args_list]
    expected = [f"SET LOCAL lock_timeout = '{COMMITTED_SESSION_LOCK_TIMEOUT}'"] if lock_timeout else []
    assert statements == expected


async def test_get_registration_after_committed_session(monkeypatch, tmp_path):
    """Test that get_registration returns the registration updated in a committed session.

    Only the Metax ID is updated, all other registrations are updated the same way.
    """
    monkeypatch.setenv("DATABASE_URL", get_sqllite_db_url(str(tmp_path / "refresh.db")))
    engine = await create_engine()
    session_factory = create_session_factory(engine)
    factory_token = session_factory_context.set(session_factory)
    repository = RegistrationRepository()
    service = RegistrationService(repository)
    request_session = session_factory()
    try:
        # Add a submission and its registration.
        async with committed_session():
            submission_id = await SubmissionRepository().add_submission(create_submission_entity())
        await service.add_registration(
            Registration(submissionId=submission_id, title="title", description="description")
        )

        # Start the request transaction, as the SessionMiddleware does, and load the registration.
        await request_session.begin()
        session_token = _session_context.set(request_session)
        try:
            registration = await repository.get_registration(submission_id)
            assert registration.metax_id is None

            # A publish step updates the registration in its own committed transaction.
            await service.update_metax_id(submission_id, "metax_id")

            # The request session returns the registration it has loaded, with the updated value.
            assert await repository.get_registration(submission_id) is registration
            assert registration.metax_id == "metax_id"
        finally:
            _session_context.reset(session_token)
    finally:
        await request_session.close()
        session_factory_context.reset(factory_token)
        await engine.dispose()
