"""Metax external service configuration."""

from pydantic import Field
from pydantic_settings import BaseSettings


class MetaxConfig(BaseSettings):
    """Metax external service configuration."""

    model_config = {"extra": "allow"}

    METAX_URL: str = Field(description="Metax URL")
    METAX_TOKEN: str = Field(description="Metax authentication token")


def metax_config() -> MetaxConfig:
    """Get Metax configuration."""

    # Avoid loading environment variables when module is imported.
    return MetaxConfig()
