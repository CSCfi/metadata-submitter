"""Crypt4GH configuration."""

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings
from typing_extensions import Self


class Crypt4GHConfig(BaseSettings):
    """
    Crypt4GH configuration.

    A deployment that writes out metadata objects after publish encrypts the metadata objects
    using CRYPT4GH_PUBLIC_KEY and a private key generated for each file.
    """

    model_config = {"extra": "allow"}  # Allow creation using the constructor.

    CRYPT4GH_PUBLIC_KEY_URL: str | None = Field(
        default=None,
        description=(
            "URL providing the PEM public Crypt4GH key for encrypting metadata objects written out after publish. "
            "Cached for one hour. Supports key rotation. Used in preference to CRYPT4GH_PUBLIC_KEY."
        ),
    )
    CRYPT4GH_PUBLIC_KEY: str | None = Field(
        default=None,
        description=(
            "Base64 encoded PEM public Crypt4GH key for encrypting metadata objects written out after publish. "
            "Alternative to CRYPT4GH_PUBLIC_KEY_URL. Does not support key rotation."
        ),
    )

    @model_validator(mode="after")
    def _check_public_key(self) -> Self:
        if not self.CRYPT4GH_PUBLIC_KEY_URL and not self.CRYPT4GH_PUBLIC_KEY:
            raise ValueError("CRYPT4GH_PUBLIC_KEY_URL or CRYPT4GH_PUBLIC_KEY is required.")
        return self


def c4gh_config() -> Crypt4GHConfig:
    """Get Crypt4GH configuration."""

    # Avoid loading environment variables when module is imported.
    return Crypt4GHConfig()
