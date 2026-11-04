"""Metax external service configuration."""

from pydantic import Field, SecretStr

from metadata_backend.conf.secret import SecretSettings


class MetaxConfig(SecretSettings):
    """Metax external service configuration."""

    model_config = {"extra": "allow"}

    METAX_URL: str = Field(description="Metax URL")
    METAX_TOKEN: SecretStr = Field(description="Metax authentication token")


def metax_config() -> MetaxConfig:
    """Get Metax configuration."""

    # Avoid loading environment variables when module is imported.
    return MetaxConfig()
