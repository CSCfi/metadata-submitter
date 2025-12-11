"""OIDC external service configuration."""

from urllib.parse import urljoin

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings


class OIDCConfig(BaseSettings):
    """OIDC external service configuration."""

    model_config = {"extra": "allow"}  # Allow creation using the constructor.

    BASE_URL: str = Field(description="Application URL")
    OIDC_URL: str = Field(description="OIDC provider URL")
    REDIRECT_URL: str | None = Field(
        default=None,
        description="OIDC redirection URL",
    )
    OIDC_CLIENT_ID: str = Field(
        description="OIDC client ID",
        validation_alias="AAI_CLIENT_ID",  # TODO(improve): rename to OIDC_CLIENT_ID
    )
    OIDC_CLIENT_SECRET: str = Field(
        description="OIDC client secret",
        validation_alias="AAI_CLIENT_SECRET",  # TODO(improve): rename to OIDC_CLIENT_SECRET
    )
    OIDC_SCOPE: str = Field(default="openid profile email", description="OIDC scopes")

    @computed_field
    def redirect_url(self) -> str:
        """Return redirect URL or base URL."""

        return self.REDIRECT_URL or self.BASE_URL

    @computed_field
    def callback_url(self) -> str:
        """Return callback URL based on base URL."""

        return urljoin(self.BASE_URL, "callback")


oidc_config = OIDCConfig()
