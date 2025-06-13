"""Unit test configuration."""

import os

import pytest

from metadata_backend.database.postgres.repository import PG_DATABASE_URL_ENV, get_sqllite_db_url


@pytest.fixture(scope="session", autouse=True)
def set_env_variables() -> None:
    """Set environment variables used by unit tests."""
    os.environ[PG_DATABASE_URL_ENV] = get_sqllite_db_url()

    # os.environ[PG_DATABASE_URL_ENV] = get_postgres_db_url(
    #     host="",
    #     port="",
    #     user="",
    #     password="",
    #     database=""
    # )
