"""BigPicture configuration."""

from pydantic import Field
from pydantic_settings import BaseSettings


class BigPictureConfig(BaseSettings):
    """BigPicture configuration."""

    model_config = {"extra": "allow"}  # Allow creation using the constructor.

    BP_CENTER_ID: str = Field(description="Accession prefix")


def bp_config() -> BigPictureConfig:
    """Get BigPicture configuration."""

    # Avoid loading environment variables when module is imported.
    return BigPictureConfig()
