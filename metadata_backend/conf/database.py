"""Database configuration."""

from pydantic import Field
from pydantic_settings import BaseSettings


class DatabaseConfig(BaseSettings):
    """Database configuration."""

    model_config = {"extra": "allow"}  # Allow creation using the constructor.

    DATABASE_URL: str = Field(description="Database URL")
    DATABASE_MIGRATE: bool = Field(
        default=False, description="Apply the Alembic migrations to the database when the server starts."
    )


def database_config() -> DatabaseConfig:
    """Get database configuration."""

    # Avoid loading environment variables when module is imported.
    return DatabaseConfig()
