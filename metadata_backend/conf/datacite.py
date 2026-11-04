"""DataCite external service configuration."""

from pydantic import Field, SecretStr

from metadata_backend.conf.secret import SecretSettings


class DataciteConfig(SecretSettings):
    """DataCite external service configuration."""

    model_config = {"extra": "allow"}  # Allow creation using the constructor.

    DATACITE_API: str = Field(description="DataCite URL")
    DATACITE_USER: str = Field(description="DataCite user")
    DATACITE_KEY: SecretStr = Field(description="DataCite user key")
    DATACITE_DOI_PREFIX: str = Field(description="DataCite DOI prefix")


def datacite_config() -> DataciteConfig:
    """Get DataCite configuration."""

    # Avoid loading environment variables when module is imported.
    return DataciteConfig()
