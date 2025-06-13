"""Postgres repositories."""

import os
from typing import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from .models import ApiKeyEntity, Base

SessionFactory = async_sessionmaker[AsyncSession]

PG_DATABASE_URL_ENV = "PG_DATABASE_URL"


async def __create_schema(engine: AsyncEngine) -> None:
    """
    Create database schema if it does not already exist.

    Args:
        engine: Asynchronous SQLAlchemy 2.0 engine.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def create_engine(db_url: str | None = None) -> AsyncEngine:
    """
    Create and return an asynchronous SQLAlchemy 2.0 engine.

    If the db_url is not provided, the PG_DATABASE_URL environment variable will be used.

    Args:
        db_url: The database URL.

    Returns:
         Asynchronous SQLAlchemy 2.0 engine.
    """

    db_url = db_url or os.getenv(PG_DATABASE_URL_ENV)
    if db_url is None:
        raise ValueError(f"Missing PostgreSQL environmental variable: {PG_DATABASE_URL_ENV}")

    engine = create_async_engine(db_url, echo=True)
    await __create_schema(engine)
    return engine


def get_postgres_db_url(host: str, port: str, user: str, password: str, database: str) -> str:
    """
    Create and return Postgres database url.

    Returns:
        Postgres database url.
    """
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"


def get_sqllite_db_url() -> str:
    """
    Create and return Sqllite in-memory database url.

    Returns:
        Sqllite in-memory database url.
    """
    return "sqlite+aiosqlite:///:memory:"


def create_session_factory(engine: AsyncEngine) -> SessionFactory:
    """
    Create session factory.

    Args:
        engine: Asynchronous SQLAlchemy 2.0 engine.

    Returns:
         Session factory.
    """
    return async_sessionmaker(engine, expire_on_commit=False)


class ApiKeyRepository:
    """Repository for the api_key table."""

    def __init__(self, session_factory: SessionFactory) -> None:
        """
        Initialize the repository with a session factory.

        Args:
            session_factory: A factory that creates async SQLAlchemy sessions.
        """
        self.__session_factory = session_factory

    async def add_api_key(self, api_key: ApiKeyEntity) -> None:
        """
        Add a new API key row to the database.

        Args:
            api_key: The API key row.
        """
        async with self.__session_factory() as session:
            async with session.begin():
                session.add(api_key)

    async def get_api_key(self, key_id: str) -> ApiKeyEntity | None:
        """
        Retrieve the API key row for a hashed API key.

        Args:
            key_id: Generated unique key id.

        Returns:
            The API key row or None if the hashed API key was not found.
        """
        async with self.__session_factory() as session:
            stmt = select(ApiKeyEntity).where(ApiKeyEntity.key_id == key_id)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            return row

    async def get_api_keys(self, user_id: str) -> Sequence[ApiKeyEntity]:
        """
        Retrieve all API key rows for a given user with the API key ids, hashes and salt masked.

        Args:
            user_id: The user id to filter API keys.

        Returns:
            A list of API key rows for the user with the API API key ids, hashes and salt masked.
        """
        async with self.__session_factory() as session:
            stmt = select(ApiKeyEntity).where(ApiKeyEntity.user_id == user_id)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            for row in rows:
                row.key_id = ""
                row.api_key = ""
                row.salt = ""
            return rows

    async def delete_api_key(self, user_id: str, user_key_id: str) -> None:
        """
        Delete an API key row matching the given user ID and hashed API key.

        Args:
            user_id: The user id whose API key should be deleted.
            user_key_id: The unique key id assigned by the user.
        """
        async with self.__session_factory() as session:
            async with session.begin():
                stmt = delete(ApiKeyEntity).where(
                    ApiKeyEntity.user_id == user_id, ApiKeyEntity.user_key_id == user_key_id
                )
                await session.execute(stmt)
