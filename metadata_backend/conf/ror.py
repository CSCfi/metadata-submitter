"""ROR external service configuration."""

from pydantic import Field
from pydantic_settings import BaseSettings


class RorConfig(BaseSettings):
    """ROR external service configuration."""

    model_config = {"extra": "allow"}  # Allow creation using the constructor.

    ROR_URL: str = Field(description="ROR API URL")  # default="https://api.ror.org/v2/"


def ror_config() -> RorConfig:
    """Get ROR configuration."""

    # Avoid loading environment variables when module is imported.
    return RorConfig()
