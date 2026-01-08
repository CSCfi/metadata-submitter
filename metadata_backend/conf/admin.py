"""NeIC SDA Admin API external service configuration."""

from pydantic import Field
from pydantic_settings import BaseSettings


class AdminConfig(BaseSettings):
    """NeIC SDA Admin API external service configuration."""

    model_config = {"extra": "allow"}  # Allow creation using the constructor.

    ADMIN_URL: str = Field(description="NeIC SDA Admin API URL")
    ADMIN_POLLING_INTERVAL: int = Field(3600, description="NeIC SDA Admin API polling interval")


def admin_config() -> AdminConfig:
    """Get NeIC SDA Admin API configuration."""

    # Avoid loading environment variables when module is imported.
    return AdminConfig()
