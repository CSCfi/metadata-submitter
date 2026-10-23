"""Deployment configuration."""

from enum import StrEnum

from pydantic import Field
from pydantic_settings import BaseSettings

from ..api.models.submission import SubmissionWorkflow


class Deployment(StrEnum):
    """Deployment type, set with the DEPLOYMENT environment variable."""

    CSC = "CSC"
    NBIS = "NBIS"

    @property
    def workflow(self) -> SubmissionWorkflow:
        """The workflow of the submissions created in the deployment."""
        match self:
            case Deployment.CSC:
                return SubmissionWorkflow.SD
            case Deployment.NBIS:
                return SubmissionWorkflow.BP


class DeploymentConfig(BaseSettings):
    """Deployment configuration."""

    API_PREFIX: str = Field(default="", description="API URL PREFIX.")
    DEPLOYMENT: Deployment = Field(default=Deployment.CSC, description="The deployment type.")
    SERVER_PORT: int | None = Field(
        default=None,
        ge=1,
        le=65535,
        description="The port the server listens on. Defaults to 5430 for CSC and 5431 for NBIS.",
    )
    ALLOW_UNSAFE: bool = Field(default=False, description="Allow published submissions to be modifiable.")
    ALLOW_REGISTRATION: bool = Field(
        default=True, description="Allow published submissions to be registered with external services."
    )
    IMPORT_USERS: list[str] = Field(
        default_factory=list,
        description="JSON array of the ids of the users allowed to import submissions accessioned outside SD Submit.",
    )

    @property
    def API_PREFIX_V1(self) -> str:
        return f"{self.API_PREFIX}/v1"

    @property
    def API_PREFIX_SYNC(self) -> str:
        return f"{self.API_PREFIX}/sync"


def deployment_config() -> DeploymentConfig:
    """Get Deployment configuration."""

    # Avoid loading environment variables when module is imported.
    return DeploymentConfig()
