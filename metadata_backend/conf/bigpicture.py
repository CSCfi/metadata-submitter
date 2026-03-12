"""Bigpicture configuration."""

from pydantic import Field
from pydantic_settings import BaseSettings


class BigpictureConfig(BaseSettings):
    """Bigpicture configuration."""

    model_config = {"extra": "allow"}  # Allow creation using the constructor.

    BP_CENTER_ID: str = Field(description="Accession prefix")


def bp_config() -> BigpictureConfig:
    """Get Bigpicture configuration."""

    # Avoid loading environment variables when module is imported.
    return BigpictureConfig()
