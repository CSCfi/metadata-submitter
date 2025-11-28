"""Unit test configuration."""

import asyncio
import atexit
import os
import tempfile
from typing import AsyncGenerator
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from metadata_backend.api.services.accession import BP_CENTER_ID_ENV
from metadata_backend.database.postgres.repositories.file import FileRepository
from metadata_backend.database.postgres.repositories.object import ObjectRepository
from metadata_backend.database.postgres.repositories.registration import RegistrationRepository
from metadata_backend.database.postgres.repositories.submission import SubmissionRepository
from metadata_backend.database.postgres.repository import (
    PG_DATABASE_URL_ENV,
    SessionFactory,
    create_engine,
    create_session_factory,
    get_sqllite_db_url,
)
from metadata_backend.database.postgres.services.file import FileService
from metadata_backend.database.postgres.services.object import ObjectService
from metadata_backend.database.postgres.services.registration import RegistrationService
from metadata_backend.database.postgres.services.submission import SubmissionService

_engine: AsyncEngine | None = None
_session_factory: SessionFactory | None = None
_submission_repository: SubmissionRepository | None = None
_object_repository: ObjectRepository | None = None
_file_repository: FileRepository | None = None
_registration_repository: RegistrationRepository | None = None

# set required S3 env vars for all tests
os.environ.setdefault("STATIC_S3_ACCESS_KEY_ID", "test")
os.environ.setdefault("STATIC_S3_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("SD_SUBMIT_PROJECT_ID", "1000")
os.environ.setdefault("S3_REGION", "us-east-1")
os.environ.setdefault("S3_ENDPOINT", "http://localhost")
os.environ.setdefault("KEYSTONE_ENDPOINT", "http://localhost")


def pytest_configure(config):
    os.environ["BASE_URL"] = "http://test.local:5430"
    os.environ["OIDC_URL"] = ""
    os.environ["AAI_CLIENT_ID"] = "public"
    os.environ["AAI_CLIENT_SECRET"] = "secret"
    os.environ[BP_CENTER_ID_ENV] = "bb"


async def _session_start():
    # Create SQLAlchemy engine and session factory.
    global _engine, _session_factory, _submission_repository, _object_repository, _file_repository, _registration_repository

    _temp_sqlite_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    atexit.register(lambda: os.remove(_temp_sqlite_file.name))

    os.environ[PG_DATABASE_URL_ENV] = get_sqllite_db_url(_temp_sqlite_file.name)
    _engine = await create_engine()
    _session_factory = create_session_factory(_engine)
    _submission_repository = SubmissionRepository(_session_factory)
    _object_repository = ObjectRepository(_session_factory)
    _file_repository = FileRepository(_session_factory)
    _registration_repository = RegistrationRepository(_session_factory)


async def _session_finish():
    if _engine:
        # Dispose SQLAlchemy engine.
        await _engine.dispose()


def pytest_sessionstart(session):
    asyncio.run(_session_start())


def pytest_sessionfinish(session, exitstatus):
    asyncio.run(_session_finish())


@pytest.fixture
async def session_factory() -> AsyncGenerator[SessionFactory, None]:
    yield _session_factory


# Repositories


@pytest.fixture
def submission_repository() -> SubmissionRepository:
    return _submission_repository


@pytest.fixture
def object_repository() -> ObjectRepository:
    return _object_repository


@pytest.fixture
def file_repository() -> FileRepository:
    return _file_repository


@pytest.fixture
def registration_repository() -> RegistrationRepository:
    return _registration_repository


# Services


@pytest.fixture
def submission_service() -> SubmissionService:
    return SubmissionService(_submission_repository, _registration_repository)


@pytest.fixture
def object_service() -> ObjectService:
    return ObjectService(_object_repository)


@pytest.fixture
def file_service() -> FileService:
    return FileService(_file_repository)


@pytest.fixture
def registration_service() -> RegistrationService:
    return RegistrationService(_registration_repository)
