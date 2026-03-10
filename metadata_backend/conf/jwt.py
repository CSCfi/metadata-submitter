"""JWT token configuration."""

from pydantic import Field
from pydantic_settings import BaseSettings


class JWTConfig(BaseSettings):
    """JWT configuration."""

    JWT_KEY: str = Field(description="Secret key used to sign and verify or public key used to verify JWT.")
    JWT_ISSUER: str = Field(
        default="SD Submit", description="Issuer claim to use when creating and verifying JWT tokens."
    )
    JWT_ALGORITHM: str = Field(default="HS256", description="Algorithm used to sign and verify JWT tokens.")


def jwt_config() -> JWTConfig:
    """Get JWT configuration."""

    # Avoid loading environment variables when module is imported.
    return JWTConfig()
