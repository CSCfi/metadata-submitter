"""Keystone external service configuration."""

from pydantic import Field
from pydantic_settings import BaseSettings


class KeystoneConfig(BaseSettings):
    """Keystone external service configuration."""

    model_config = {"extra": "allow"}  # Allow creation using the constructor.

    KEYSTONE_ENDPOINT: str = Field(description="Keystone service endpoint URL")


def keystone_config() -> KeystoneConfig:
    """Get Keystone configuration."""

    # Avoid loading environment variables when module is imported.
    return KeystoneConfig()
