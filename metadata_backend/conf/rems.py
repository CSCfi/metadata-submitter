"""REMS external service configuration."""

from pydantic import Field
from pydantic_settings import BaseSettings


class RemsConfig(BaseSettings):
    """REMS external service configuration."""

    model_config = {"extra": "allow"}  # Allow creation using the constructor.

    REMS_URL: str = Field(description="REMS API URL")
    REMS_USER: str = Field(description="REMS API user")
    REMS_KEY: str = Field(description="REMS API key")
    REMS_DISCOVERY_URL: str = Field(description="REMS discovery URL")


def rems_config() -> RemsConfig:
    """Get REMS configuration."""

    # Avoid loading environment variables when module is imported.
    return RemsConfig()
