"""CSC LDAP external service configuration."""

from pydantic import Field
from pydantic_settings import BaseSettings


class CscLdapConfig(BaseSettings):
    """CSC LDAP external service configuration."""

    model_config = {"extra": "allow"}  # Allow creation using the constructor.

    CSC_LDAP_HOST: str = Field(description="CSC LDAP host")
    CSC_LDAP_USER: str = Field(description="CSC LDAP user")
    CSC_LDAP_PASSWORD: str = Field(description="CSC LDAP password")


def csc_ldap_config() -> CscLdapConfig:
    """Get CSC LDAP configuration."""

    # Avoid loading environment variables when module is imported.
    return CscLdapConfig()
