"""CSC PID external service configuration."""

from pydantic import Field, SecretStr

from metadata_backend.conf.secret import SecretSettings


class CscPidConfig(SecretSettings):
    """CSC PID external service configuration."""

    model_config = {"extra": "allow"}  # Allow creation using the constructor.

    CSC_PID_URL: str = Field(description="CSC PID URL")
    CSC_PID_KEY: SecretStr = Field(description="CSC PID KEY")


def csc_pid_config() -> CscPidConfig:
    """Get CSC PID configuration."""

    # Avoid loading environment variables when module is imported.
    return CscPidConfig()
