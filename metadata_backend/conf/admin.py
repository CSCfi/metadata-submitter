"""NeIC SDA Admin API external service configuration."""

from pydantic import Field
from pydantic_settings import BaseSettings


class AdminConfig(BaseSettings):
    """NeIC SDA Admin API external service configuration."""

    model_config = {"extra": "allow"}  # Allow creation using the constructor.

    ADMIN_URL: str = Field(description="NeIC SDA Admin API URL")
    ADMIN_TOKEN: str = Field(description="NeIC SDA Admin API bearer token")
    INGEST_SCAN_INTERVAL: int = Field(
        60,
        description="Background ingest scanner interval in seconds.",
    )
    INGEST_WORKERS: int = Field(4, description="Maximum number of concurrent background ingest workers.")


def admin_config() -> AdminConfig:
    """Get NeIC SDA Admin API configuration."""

    # Avoid loading environment variables when module is imported.
    return AdminConfig()
