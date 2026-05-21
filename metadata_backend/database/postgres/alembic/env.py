"""Alembic environment configuration."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import URL, make_url

from metadata_backend.conf.database import database_config
from metadata_backend.database.postgres.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


target_metadata = Base.metadata


def _get_sync_database_url() -> str:
    """Return a synchronous database URL for Alembic."""
    url = make_url(database_config().DATABASE_URL)

    driver_map = {
        "postgresql+asyncpg": "postgresql+psycopg",
        "sqlite+aiosqlite": "sqlite",
    }
    if url.drivername in driver_map:
        url = url.set(drivername=driver_map[url.drivername])

    return URL.render_as_string(url, hide_password=False)


def run_migrations_offline() -> None:
    """Run migrations in offline mode."""
    context.configure(
        url=_get_sync_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in online mode."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _get_sync_database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
