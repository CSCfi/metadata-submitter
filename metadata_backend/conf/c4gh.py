"""Crypt4GH configuration."""

from pydantic import Field
from pydantic_settings import BaseSettings


class Crypt4GHConfig(BaseSettings):
    """Crypt4GH configuration."""

    model_config = {"extra": "allow"}  # Allow creation using the constructor.

    SENDER_SECRET_KEY: str = Field(description="Base64 encoded private Crypt4GH key")
    SECRET_KEY_PASSPHRASE: str = Field(description="Secret key passphrase")
    BP_PUBLIC_C4GH_KEY: str = Field(description="Base64 encoded public Crypt4GH key for Bigpicture")


def c4gh_config() -> Crypt4GHConfig:
    """Get Crypt4GH configuration."""

    # Avoid loading environment variables when module is imported.
    return Crypt4GHConfig()
