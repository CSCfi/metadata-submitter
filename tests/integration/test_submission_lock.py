"""Test the submission lock against a temporary PostgreSQL database."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

from metadata_backend.database.postgres.repositories.registration import RegistrationRepository
from metadata_backend.database.postgres.repositories.submission import SubmissionRepository
from metadata_backend.database.postgres.repository import (
    SessionFactory,
    _session_context,
    create_engine,
    create_session_factory,
)
from metadata_backend.database.postgres.services.submission import LockedSubmissionUserException, SubmissionService
from tests.unit.database.postgres.helpers import create_submission_entity

from .conf import nbis_database_url

pytestmark = pytest.mark.skipif(nbis_database_url is None, reason="Needs the NBIS database server.")


@asynccontextmanager
async def _transaction(session_factory: SessionFactory) -> AsyncIterator[None]:
    """Run the block in a new transaction, as the SessionMiddleware does for a request."""
    async with session_factory() as _session, _session.begin():
        token = _session_context.set(_session)
        try:
            yield
        finally:
            _session_context.reset(token)


async def test_lock_submission(temp_nbis_database_url):
    """Test that a submission locked by another transaction fails at once with a conflict, rather than waiting."""
    engine = await create_engine()
    session_factory = create_session_factory(engine)
    service = SubmissionService(SubmissionRepository(), RegistrationRepository())
    try:
        async with _transaction(session_factory):
            submission_id = await service.repository.add_submission(create_submission_entity())

        async with _transaction(session_factory):
            await service.lock_submission(submission_id)

            # Another transaction can't lock the submission while the first one holds the lock.
            async with _transaction(session_factory):
                with pytest.raises(LockedSubmissionUserException) as exc_info:
                    await service.lock_submission(submission_id)
                assert exc_info.value.status_code == 409

        # The lock is released when the transaction ends.
        async with _transaction(session_factory):
            await service.lock_submission(submission_id)
    finally:
        await engine.dispose()
