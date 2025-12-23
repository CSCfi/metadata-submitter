"""S3 storage configuration."""

from pydantic import Field
from pydantic_settings import BaseSettings


class S3Config(BaseSettings):
    """S3 storage configuration."""

    model_config = {"extra": "allow"}  # Allow creation using the constructor.

    STATIC_S3_ACCESS_KEY_ID: str = Field(description="S3 access key ID for static credentials")
    STATIC_S3_SECRET_ACCESS_KEY: str = Field(description="S3 secret access key for static credentials")
    SD_SUBMIT_PROJECT_ID: str = Field(description="SD Submit project ID for S3 bucket policies")
    S3_REGION: str = Field(description="S3 region")
    S3_ENDPOINT: str = Field(description="S3 endpoint URL")


s3_config = S3Config()
