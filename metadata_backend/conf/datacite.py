"""DataCite external service configuration."""

from pydantic import Field
from pydantic_settings import BaseSettings


class DataciteConfig(BaseSettings):
    """DataCite external service configuration."""

    model_config = {"extra": "allow"}  # Allow creation using the constructor.

    DATACITE_API: str = Field(description="DataCite URL")
    DATACITE_USER: str = Field(description="DataCite user")
    DATACITE_KEY: str = Field(description="DataCite user key")
    DATACITE_DOI_PREFIX: str = Field(description="DataCite DOI prefix")


def datacite_config() -> DataciteConfig:
    """Get DataCite configuration."""

    # Avoid loading environment variables when module is imported.
    return DataciteConfig()
