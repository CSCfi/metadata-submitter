"""Metax external service configuration."""

from pydantic import Field
from pydantic_settings import BaseSettings


class MetaxConfig(BaseSettings):
    """Metax external service configuration."""

    model_config = {"extra": "allow"}

    METAX_URL: str = Field(description="Metax URL")
    METAX_TOKEN: str = Field(description="Metax authentication token")


metax_config = MetaxConfig()
