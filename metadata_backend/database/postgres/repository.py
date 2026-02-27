"""Postgres session."""

import os
import re
import sqlite3
from contextvars import ContextVar
from typing import Callable

from sqlalchemy import create_mock_engine, event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from ...api.exceptions import SystemException
from ...conf.database import database_config
from .models import Base

SessionFactory = async_sessionmaker[AsyncSession]


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

    If the db_url is not provided, the DATABASE_URL environment variable will be used.

    Args:
        db_url: The database URL.

    Returns:
         Asynchronous SQLAlchemy 2.0 engine.
    """

    if db_url is None:
        db_url = database_config().DATABASE_URL

    engine = create_async_engine(db_url, echo=False)

    # Enable foreign keys in SQLite.
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine.sync_engine, "connect")
        def set_sqlite_pragma(dbapi_connection: sqlite3.Connection, _: object) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    await _create_schema(engine)
    return engine


async def is_healthy(session_factory_provider: Callable[[], SessionFactory]) -> bool:
    session_factory = session_factory_provider()
    async with session_factory() as _session:
        try:
            await _session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False


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
        sqls.append(re.sub(r"[ \t]+$", "", sql, flags=re.MULTILINE).rstrip() + ";")

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
    return async_sessionmaker(bind=engine, expire_on_commit=False)


# Holds the database AsyncSession for each request in a task-local context variable. The
# AsyncSession is added and removed from the context variable, and the transaction is managed,
# by the SessionMiddleware. The transaction is started before the request processing beings,
# and ended after the request processing is completed but before the response is sent back.
_session_context: ContextVar[AsyncSession | None] = ContextVar("_session_context", default=None)


def session() -> AsyncSession:
    """
    Return an existing task-scoped AsyncSession.
    """
    _session = _session_context.get(None)
    if _session is None:
        raise SystemException("No active transaction")
    return _session


# python -m metadata_backend.database.postgres.repository
if __name__ == "__main__":
    save_schema()
