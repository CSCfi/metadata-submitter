"""Deployment configuration."""

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings


class DeploymentConfig(BaseSettings):
    """Deployment configuration."""

    DEPLOYMENT: Literal["CSC", "NBIS"] = Field(default="CSC", description="The deployment type.")
    ALLOW_UNSAFE: bool = Field(default=False, description="Allow published submissions to be modifiable.")
    ALLOW_REGISTRATION: bool = Field(
        default=True, description="Allow published submissions to be registered with external services."
    )
    JWT_KEY: str = Field(description="Secret key used to sign and verify or public key used to verify JWT.")
    JWT_ISSUER: str = Field(
        default="SD Submit", description="Issuer claim to use when creating and verifying JWT tokens."
    )


def deployment_config() -> DeploymentConfig:
    """Get Deployment configuration."""

    # Avoid loading environment variables when module is imported.
    return DeploymentConfig()
