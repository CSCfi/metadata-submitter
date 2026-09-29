"""OpenBao configuration."""

from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings
from typing_extensions import Self

# Defines how a metadata object is encrypted when it is stored in the database.
#
#    envelope  OpenBao generates a data encryption key for this one object. The
#               document is encrypted with that key, while the key itself is
#               encrypted by OpenBao under a key encryption key. The stored
#               object contains both the encrypted data encryption key,
#               and the encrypted document.
#
#     direct    The document is sent to OpenBao and comes back encrypted. The
#               stored object contains the encrypted document. Only a symmetric
#               encryption key can be used for direct encryption. An asymmetric
#               key encryption key can only encrypt at most a few hundred bytes.

ObjectEncryption = Literal["envelope", "direct"]

ENVELOPE: ObjectEncryption = "envelope"
DIRECT: ObjectEncryption = "direct"


class OpenBaoConfig(BaseSettings):
    """OpenBao configuration."""

    model_config = {"extra": "allow"}  # Allow creation using the constructor.

    OPENBAO_URL: str | None = Field(
        default=None,
        description=(
            "URL of the OpenBao server. Defining it makes a deployment encrypt the metadata "
            "objects it stores in the database."
        ),
    )
    OPENBAO_TOKEN: str | None = Field(
        default=None,
        description="OpenBao server token. The alternative to OPENBAO_KUBERNETES_ROLE.",
    )
    OPENBAO_KUBERNETES_ROLE: str | None = Field(
        default=None,
        description=(
            "Name of the OpenBao role a Kubernetes service account authenticates with. "
            "Required for service account authentication."
        ),
    )
    OPENBAO_KUBERNETES_MOUNT: str = Field(
        default="kubernetes",
        description="Where OpenBao mounts the Kubernetes authentication method.",
    )
    OPENBAO_OBJECT_KEY_NAME: str | None = Field(
        default=None,
        description=(
            "Name of OpenBao encryption key that metadata objects are encrypted with. "
            "Required when OPENBAO_URL is defined."
        ),
    )
    OPENBAO_OBJECT_ENCRYPTION: ObjectEncryption = Field(
        default=ENVELOPE,
        description=(
            "How metadata objects are encrypted. "
            "envelope: OpenBao generates a data encryption key for each metadata object. The "
            "object is encrypted with that key, while the key itself is "
            "encrypted by OpenBao under a key encryption key. The stored "
            "object contains both the encrypted data encryption key, "
            "and the encrypted document. "
            "direct: The object is sent to OpenBao and comes back encrypted by an "
            "encryption key. The stored object contains the encrypted "
            "document. Only a symmetric key encryption key can be used for "
            "direct encryption."
        ),
    )

    @model_validator(mode="after")
    def _check_key_name(self) -> Self:
        if self.OPENBAO_URL and not self.OPENBAO_OBJECT_KEY_NAME:
            raise ValueError("OPENBAO_OBJECT_KEY_NAME is required when OPENBAO_URL is defined.")
        return self

    @model_validator(mode="after")
    def _check_authentication(self) -> Self:
        if self.OPENBAO_URL and bool(self.OPENBAO_TOKEN) == bool(self.OPENBAO_KUBERNETES_ROLE):
            raise ValueError(
                "Exactly one of OPENBAO_TOKEN and OPENBAO_KUBERNETES_ROLE is required when OPENBAO_URL is defined."
            )
        return self


def openbao_config() -> OpenBaoConfig:
    """Get OpenBao configuration."""

    # Avoid loading environment variables when module is imported.
    return OpenBaoConfig()
