"""Postgres session."""

import os
import re
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Callable

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, create_mock_engine, event, inspect, pool, text
from sqlalchemy import create_engine as create_sync_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from ...api.exceptions import SystemException
from ...conf.database import database_config
from .models import Base

SessionFactory = async_sessionmaker[AsyncSession]

_ALEMBIC_DIR = Path(__file__).parent / "alembic"


def _alembic_config() -> Config:
    """Return the Alembic configuration."""
    config = Config()
    config.set_main_option("script_location", str(_ALEMBIC_DIR))
    return config


def _has_tables(connection: Connection) -> bool:
    """Return true if any of the database tables have already been created."""
    return not set(inspect(connection).get_table_names()).isdisjoint(Base.metadata.tables)


def _create_tables(connection: Connection) -> None:
    """
    Create the tables from the models if the database has none and
    stamp the latest Alembic revision.

    Args:
        connection: Synchronous SQLAlchemy connection.
    """
    if _has_tables(connection):
        return

    Base.metadata.create_all(connection)
    script_dir = ScriptDirectory.from_config(_alembic_config())
    MigrationContext.configure(connection).stamp(script_dir, "head")


async def _create_schema(engine: AsyncEngine) -> None:
    """
    Create database schema if the none of the tables already exist.

    Args:
        engine: Asynchronous SQLAlchemy 2.0 engine.
    """
    async with engine.begin() as conn:
        await conn.run_sync(_create_tables)


def get_sync_database_url() -> str:
    """Return the database URL given by the DATABASE_URL environment variable with a synchronous driver."""
    url = make_url(database_config().DATABASE_URL)

    driver_map = {
        "postgresql+asyncpg": "postgresql+psycopg",
        "sqlite+aiosqlite": "sqlite",
    }
    if url.drivername in driver_map:
        url = url.set(drivername=driver_map[url.drivername])

    return URL.render_as_string(url, hide_password=False)


def migrate_schema() -> None:
    """
    Apply the Alembic migrations to the database given by the DATABASE_URL environment variable.

    Checks that database tables have been created.

    Run before the server starts its event loop.
    """

    engine = create_sync_engine(get_sync_database_url(), poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            has_tables = _has_tables(connection)
    finally:
        engine.dispose()

    if has_tables:
        command.upgrade(_alembic_config(), "head")


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

    # Hide bound parameters from SQL errors: they carry metadata documents and identifiers.
    engine = create_async_engine(db_url, pool_pre_ping=True, echo=False, hide_parameters=True)

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


def get_sqllite_db_url(file: str) -> str:
    """
    Create and return Sqllite database url.

    Args:
        file: the file path
    Returns:
        Sqllite file database url.
    """
    return f"sqlite+aiosqlite:///{file}"


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

# Holds the session factory for each request, set by the SessionMiddleware alongside the session,
# so that committed_session can create a separate transaction.
session_factory_context: ContextVar[SessionFactory | None] = ContextVar("session_factory_context", default=None)

# Lets committed_session run its block in the caller's transaction when there is no session factory,
# for example in the unit tests.
allow_no_committed_session: ContextVar[bool] = ContextVar("allow_no_committed_session", default=False)

# How long committed_session waits for a row lock before it fails.
COMMITTED_SESSION_LOCK_TIMEOUT = "10s"


def session() -> AsyncSession:
    """
    Return an existing task-scoped AsyncSession.
    """
    _session = _session_context.get(None)
    if _session is None:
        raise SystemException("No active transaction")
    return _session


@asynccontextmanager
async def committed_session() -> AsyncIterator[None]:
    """
    Run the block in a new transaction that is committed when the block exits.

    Without a session factory, raises unless allow_no_committed_session is set.
    """
    session_factory = session_factory_context.get(None)
    if session_factory is None:
        if not allow_no_committed_session.get():
            raise SystemException("No session factory has been defined")
        # Run the block in the caller's transaction.
        yield
        return

    # The transaction is committed when the block exits, or rolled back if it raises.
    async with session_factory() as _session, _session.begin():
        if _session.bind.dialect.name == "postgresql":
            await _session.execute(text(f"SET LOCAL lock_timeout = '{COMMITTED_SESSION_LOCK_TIMEOUT}'"))
        token = _session_context.set(_session)
        try:
            yield
        finally:
            _session_context.reset(token)


# python -m metadata_backend.database.postgres.repository
if __name__ == "__main__":
    save_schema()
