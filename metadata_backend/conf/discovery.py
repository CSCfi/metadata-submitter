"""Discovery URL configuration."""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class DiscoveryConfig(BaseSettings):
    """Discovery URL configuration."""

    model_config = {"extra": "allow"}  # Allow creation using the constructor.

    DISCOVERY_URL: str = Field(
        description="Discovery URL that points to the submission. Must contain {id} placeholder."
    )

    @field_validator("DISCOVERY_URL")
    @classmethod
    def discovery_url_validator(cls: type["DiscoveryConfig"], value: str) -> str:
        if "{id}" not in value:
            raise ValueError("DISCOVERY_URL must contain '{id}' placeholder")
        return value


def discovery_config() -> DiscoveryConfig:
    """Get discovery URL configuration."""

    # Avoid loading environment variables when module is imported.
    return DiscoveryConfig()
