"""Deployment configuration."""

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings


class DeploymentConfig(BaseSettings):
    """Deployment configuration."""

    API_PREFIX: str = Field(default="", description="API URL PREFIX.")
    DEPLOYMENT: Literal["CSC", "NBIS"] = Field(default="CSC", description="The deployment type.")
    ALLOW_UNSAFE: bool = Field(default=False, description="Allow published submissions to be modifiable.")
    ALLOW_REGISTRATION: bool = Field(
        default=True, description="Allow published submissions to be registered with external services."
    )

    @property
    def API_PREFIX_V1(self) -> str:
        return f"{self.API_PREFIX}/v1"


def deployment_config() -> DeploymentConfig:
    """Get Deployment configuration."""

    # Avoid loading environment variables when module is imported.
    return DeploymentConfig()
