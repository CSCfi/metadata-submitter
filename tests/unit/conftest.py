"""Unit test configuration."""

import asyncio
import atexit
import os
import tempfile
from typing import AsyncGenerator

import pytest
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine

from metadata_backend.conf.admin import AdminConfig
from metadata_backend.conf.bigpicture import BigPictureConfig
from metadata_backend.conf.database import DatabaseConfig
from metadata_backend.conf.datacite import DataciteConfig
from metadata_backend.conf.keystone import KeystoneConfig
from metadata_backend.conf.ldap import CscLdapConfig
from metadata_backend.conf.metax import MetaxConfig
from metadata_backend.conf.oidc import OIDCConfig
from metadata_backend.conf.pid import CscPidConfig
from metadata_backend.conf.rems import RemsConfig
from metadata_backend.conf.ror import RorConfig
from metadata_backend.conf.s3 import S3Config
from metadata_backend.database.postgres.repositories.file import FileRepository
from metadata_backend.database.postgres.repositories.object import ObjectRepository
from metadata_backend.database.postgres.repositories.registration import RegistrationRepository
from metadata_backend.database.postgres.repositories.submission import SubmissionRepository
from metadata_backend.database.postgres.repository import (
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


def pytest_configure(config):
    def _init_mandatory_envs(_confs: list[type[BaseModel]]) -> None:
        """
        Initialize mandatory environmental variables.

        These environmental variables are not meant to configure functional services
        in unit tests but are required for the associated services to be initialized.
        These services should be mocked in unit tests and tested fully in integration
        tests.
        """
        for _conf_cls in _confs:
            for _name, _field in _conf_cls.model_fields.items():
                if _field.annotation is str:
                    # Initialize mandatory string fields.
                    os.environ[_name] = "test"

    _init_mandatory_envs(
        [
            DatabaseConfig,
            DataciteConfig,
            CscPidConfig,
            CscLdapConfig,
            MetaxConfig,
            RemsConfig,
            S3Config,
            KeystoneConfig,
            OIDCConfig,
            AdminConfig,
            BigPictureConfig,
            RorConfig,
        ]
    )

    # Initialize mandatory environmental variables with specific validation rules.
    os.environ["CSC_LDAP_HOST"] = "ldap://test"
    os.environ["S3_REGION"] = "us-east-1"


# Postgres session.
#


async def _session_start():
    # Create SQLAlchemy engine and session factory.
    global \
        _engine, \
        _session_factory, \
        _submission_repository, \
        _object_repository, \
        _file_repository, \
        _registration_repository

    # Use SQLLite database.
    _temp_sqlite_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    atexit.register(lambda: os.remove(_temp_sqlite_file.name))

    os.environ["DATABASE_URL"] = get_sqllite_db_url(_temp_sqlite_file.name)

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


# Database session fixture.


@pytest.fixture
async def session_factory() -> AsyncGenerator[SessionFactory, None]:
    yield _session_factory


# Database repository fixtures.


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


# Database service fixtures.


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
