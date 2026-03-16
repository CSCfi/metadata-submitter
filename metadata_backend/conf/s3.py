"""S3 storage configuration."""

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class S3Config(BaseSettings):
    """S3 storage configuration."""

    model_config = {"extra": "allow"}  # Allow creation using the constructor.

    STATIC_S3_ACCESS_KEY_ID: Optional[str] = Field(
        default=None, description="S3 access key ID for static credentials (CSC deployment)"
    )
    STATIC_S3_SECRET_ACCESS_KEY: Optional[str] = Field(
        default=None, description="S3 secret access key for static credentials (CSC deployment)"
    )
    SD_SUBMIT_PROJECT_ID: Optional[str] = Field(
        default=None, description="SD Submit project ID for S3 bucket policies (CSC deployment)"
    )
    S3_REGION: str = Field(description="S3 region")
    S3_ENDPOINT: str = Field(description="S3 endpoint URL")


def s3_config() -> S3Config:
    """Get S3 configuration."""

    # Avoid loading environment variables when module is imported.
    return S3Config()
