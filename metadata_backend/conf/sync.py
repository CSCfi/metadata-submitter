"""Sync service account configuration."""

import base64

from cryptography.hazmat.primitives.asymmetric.ec import SECP256R1, EllipticCurvePublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings


class SyncClient(BaseModel):
    """One service allowed to sync, and the keys its tokens are signed with."""

    iss: str = Field(description="Issuer claim the tokens of this service are issued by, naming it.")
    public_keys: list[str] = Field(
        min_length=1,
        description=(
            "Base64-encoded PEM P-256 public keys verifying the tokens signed by this client. "
            "Every one is accepted, to support signing key rotation."
        ),
    )

    @field_validator("public_keys")
    @classmethod
    def decode_public_keys(cls, value: list[str]) -> list[str]:
        """Decode and parse the base64-encoded PEM public keys."""
        keys = []
        for encoded in value:
            try:
                key = base64.b64decode(encoded, validate=True).decode("utf-8")
            except Exception as exc:
                raise ValueError("public_keys must be valid base64-encoded strings") from exc
            # Parsed here to verify keys during startup.
            try:
                parsed = load_pem_public_key(key.encode("utf-8"))
            except Exception as exc:
                raise ValueError("public_keys must decode to PEM public keys") from exc
            # The sync tokens are signed with ES256, which only a P-256 key verifies.
            # A key of any other kind makes jwt.decode raise rather than reject the
            # token.
            if not isinstance(parsed, EllipticCurvePublicKey) or not isinstance(parsed.curve, SECP256R1):
                raise ValueError("public_keys must decode to P-256 elliptic curve public keys")
            keys.append(key)
        return keys


class SyncConfig(BaseSettings):
    """Sync service account configuration."""

    model_config = {"extra": "allow"}  # Allow creation using the constructor.

    SYNC_CLIENTS: list[SyncClient] = Field(
        default_factory=list,
        description=(
            "The services allowed to sync, as a JSON array of objects with an 'iss' and "
            "'public_keys'. Required to expose the sync endpoints."
        ),
    )
    SYNC_AUDIENCE: str | None = Field(
        None,
        description="Audience the sync tokens must be issued for. ",
    )

    @model_validator(mode="after")
    def validate_clients(self) -> "SyncConfig":
        if self.SYNC_CLIENTS:
            if not self.SYNC_AUDIENCE:
                raise ValueError("SYNC_AUDIENCE is required when SYNC_CLIENTS is set")
        return self


def sync_config() -> SyncConfig:
    """Get sync service account configuration."""

    # Avoid loading environment variables when module is imported.
    return SyncConfig()
