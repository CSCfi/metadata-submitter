"""Postgres repositories."""

import os
from typing import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from .models import ApiKey, Base

SessionFactory = async_sessionmaker[AsyncSession]


async def __create_schema(engine: AsyncEngine) -> None:
    """
    Create database schema if it does not already exist.

    Args:
        engine: Asynchronous SQLAlchemy 2.0 engine.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def __create_engine(db_url: str) -> AsyncEngine:
    """
    Create and return an asynchronous SQLAlchemy 2.0 engine.

    Args:
        db_url: The database URL (postgresql+psycopg://user:pass@host/dbname or sqlite+aiosqlite:///:memory).

    Returns:
         Asynchronous SQLAlchemy 2.0 engine.
    """
    engine = create_async_engine(db_url, echo=True)
    await __create_schema(engine)
    return engine


async def create_postgres_engine(
    host: str | None = None,
    port: str | None = None,
    user: str | None = None,
    password: str | None = None,
    database: str | None = None,
) -> AsyncEngine:
    """
    Create and return an asynchronous SQLAlchemy 2.0 engine using PostgreSQL.

    Parameters can be provided as arguments or are loaded from environment variables:
        - PG_HOST
        - PG_PORT
        - PG_USER
        - PG_PASSWORD
        - PG_DB

    Returns:
        AsyncEngine: Asynchronous SQLAlchemy engine.
    """
    host = host or os.getenv("PG_HOST")
    port = port or os.getenv("PG_PORT", "5432")
    user = user or os.getenv("PG_USER")
    password = password or os.getenv("PG_PASSWORD")
    database = database or os.getenv("PG_DB")

    required = {
        "PG_HOST": host,
        "PG_PORT": port,
        "PG_USER": user,
        "PG_PASSWORD": password,
        "PG_DB": database,
    }

    if missing := [k for k, v in required.items() if not v]:
        raise ValueError(f"Missing PostgreSQL environmental variables: {', '.join(missing)}")

    return await __create_engine(f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}")


async def create_sqllite_engine() -> AsyncEngine:
    """
    Create and return an asynchronous SQLAlchemy 2.0 engine using SQLLite.

    Returns:
         Asynchronous SQLAlchemy 2.0 engine.
    """
    return await __create_engine("sqlite+aiosqlite:///:memory:")


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

    async def add_api_key(self, api_key: ApiKey) -> None:
        """
        Add a new API key row to the database.

        Args:
            api_key: The API key row.
        """
        async with self.__session_factory() as session:
            async with session.begin():
                session.add(api_key)

    async def get_api_key(self, key_id: str) -> ApiKey | None:
        """
        Retrieve the API key row for a hashed API key.

        Args:
            key_id: Generated unique key id.

        Returns:
            The API key row or None if the hashed API key was not found.
        """
        async with self.__session_factory() as session:
            stmt = select(ApiKey).where(ApiKey.key_id == key_id)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            return row

    async def get_api_keys(self, user_id: str) -> Sequence[ApiKey]:
        """
        Retrieve all API key rows for a given user with the API key ids, hashes and salt masked.

        Args:
            user_id: The user id to filter API keys.

        Returns:
            A list of API key rows for the user with the API API key ids, hashes and salt masked.
        """
        async with self.__session_factory() as session:
            stmt = select(ApiKey).where(ApiKey.user_id == user_id)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            for row in rows:
                row.key_id = ""
                row.api_key = ""
                row.salt = ""
            return rows

    async def delete_api_key(self, user_id: str, key_id: str) -> None:
        """
        Delete an API key row matching the given user ID and hashed API key.

        Args:
            user_id: The user id whose API key should be deleted.
            key_id: Generated unique key id.
        """
        async with self.__session_factory() as session:
            async with session.begin():
                stmt = delete(ApiKey).where(ApiKey.user_id == user_id, ApiKey.key_id == key_id)
                await session.execute(stmt)
