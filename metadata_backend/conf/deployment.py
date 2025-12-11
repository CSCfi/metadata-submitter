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


deployment_config = DeploymentConfig()
