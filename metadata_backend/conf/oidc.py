"""OIDC external service configuration."""

from urllib.parse import urljoin

from pydantic import Field
from pydantic_settings import BaseSettings


class OIDCConfig(BaseSettings):
    """OIDC external service configuration."""

    model_config = {"extra": "allow"}  # Allow creation using the constructor.

    BASE_URL: str = Field(description="Application base URL. Used when sending callback URL to the OIDC server.")
    OIDC_URL: str = Field(description="OIDC provider URL")
    OIDC_REDIRECT_URL: str = Field(description="The URL where the user is redirected in the OIDC callback.")
    OIDC_CLIENT_ID: str = Field(
        description="OIDC client ID",
        validation_alias="OIDC_CLIENT_ID",
    )
    OIDC_CLIENT_SECRET: str = Field(
        description="OIDC client secret",
        validation_alias="OIDC_CLIENT_SECRET",
    )
    OIDC_SCOPE: str = Field(default="openid profile email", description="OIDC scopes")
    JWT_SECRET: str = Field(description="Secret key used to sign and verify JWT")
    OIDC_DPOP: bool = Field(
        default=False, description="Enables DPoP (Demonstration of Proof-of-Possession) for OIDC requests."
    )

    OIDC_VERIFY_ID_TOKEN: bool = Field(
        default=True, description="Allow unsigned ID tokens. NEVER disable in production."
    )

    @property
    def callback_url(self) -> str:
        """Get callback URL."""
        return urljoin(self.BASE_URL, "callback")


def oidc_config() -> OIDCConfig:
    """Get OIDC configuration."""

    # Avoid loading environment variables when module is imported.
    return OIDCConfig()
