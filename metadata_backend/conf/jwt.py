"""JWT token configuration."""

import base64

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class JWTConfig(BaseSettings):
    """JWT configuration."""

    JWT_KEY: str = Field(description="Secret key used to sign and verify or public key used to verify JWT.")
    JWT_ISSUER: str = Field(
        default="SD Submit", description="Issuer claim to use when creating and verifying JWT tokens."
    )
    JWT_ALGORITHM: str = Field(default="HS256", description="Algorithm used to sign and verify JWT tokens.")

    @field_validator("JWT_KEY")
    @classmethod
    def decode_jwt_key(cls: type["JWTConfig"], value: str) -> str:
        """Decode JWT key from base64-encoded environment variable."""
        try:
            decoded = base64.b64decode(value, validate=True)
            return decoded.decode("utf-8")
        except Exception as exc:
            raise ValueError("JWT_KEY must be a valid base64-encoded string") from exc


def jwt_config() -> JWTConfig:
    """Get JWT configuration."""

    # Avoid loading environment variables when module is imported.
    return JWTConfig()
