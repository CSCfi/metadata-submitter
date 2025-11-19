"""Postgres session."""

import os
import sqlite3
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import AsyncIterator, TypeVar

from sqlalchemy import create_mock_engine, event
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

    # Enable foreign keys in SQLite.
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine.sync_engine, "connect")
        def set_sqlite_pragma(dbapi_connection: sqlite3.Connection, _: object) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    await _create_schema(engine)
    return engine


def save_schema(db_url: str = "postgresql+psycopg2://") -> None:
    """
    Save the SQL to create the schema.

    Args:
        db_url: The database URL.
    """

    sqls: list[str] = []

    # https://docs.sqlalchemy.org/en/20/core/engines.html#sqlalchemy.create_mock_engine
    def _compile_sql(_expr, _, *__, **___):  # type: ignore
        sql = str(_expr.compile(dialect=engine.dialect))
        print(sql)
        sqls.append(sql)

    engine = create_mock_engine(db_url, _compile_sql)
    Base.metadata.create_all(engine, checkfirst=False)

    schema_dir = os.path.join(os.path.dirname(__file__), "schema")
    os.makedirs(schema_dir, exist_ok=True)

    output_file = os.path.join(schema_dir, "create.sql")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(sqls))


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


# python -m metadata_backend.database.postgres.repository
if __name__ == "__main__":
    save_schema()
