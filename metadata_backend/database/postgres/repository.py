"""Postgres session."""

import os
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import AsyncIterator, TypeVar

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from .models import Base

SessionFactory = async_sessionmaker[AsyncSession]

PG_DATABASE_URL_ENV = "PG_DATABASE_URL"


async def _create_schema(engine: AsyncEngine) -> None:
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
    await _create_schema(engine)
    return engine


def get_postgres_db_url(host: str, port: int, user: str, password: str, database: str) -> str:
    """
    Create and return Postgres database url.

    Returns:
        Postgres database url.
    """
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"


def get_sqllite_db_url(file: str) -> str:
    """
    Create and return Sqllite database url.

    Args:
        file: the file path
    Returns:
        Sqllite in-memory database url.
    """
    return f"sqlite+aiosqlite:///{file}?cache=shared"


def create_session_factory(engine: AsyncEngine) -> SessionFactory:
    """
    Create session factory.

    Args:
        engine: Asynchronous SQLAlchemy 2.0 engine.

    Returns:
         Session factory.
    """
    return async_sessionmaker(engine, expire_on_commit=False)


TRANSACTION_T = TypeVar("TRANSACTION_T")

_session_context: ContextVar[AsyncSession | None] = ContextVar("_session_context", default=None)


@asynccontextmanager
async def transaction(
    session_factory: SessionFactory, requires_new: bool = False, rollback_new: bool = False
) -> AsyncIterator[AsyncSession]:
    """
    Transactional SQLAlchemy session.

    Args:
        session_factory: The session factory.
        requires_new: Is a new SQLAlchemy transaction required.
        rollback_new: If a new SQLAlchemy session is created then rollback the transaction.
    """
    if not requires_new:
        existing_session = _session_context.get()

        if existing_session is not None:
            # Active session.
            yield existing_session
            return

    # Start a new session.
    async with session_factory() as session:
        token = _session_context.set(session)
        try:
            async with session.begin():
                yield session
                if rollback_new:
                    await session.rollback()
        finally:
            _session_context.reset(token)
