"""Logging configuration."""

from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LogFormat = Literal["TEXT", "JSON"]


class LogConfig(BaseSettings):
    """Logging configuration."""

    # Allow creation using the constructor, and treat an empty variable as not set.
    model_config = {"extra": "allow", "env_ignore_empty": True}

    LOG_LEVEL: LogLevel = Field(
        default="INFO",
        description=(
            "Level of the server log: 'DEBUG', 'INFO', 'WARNING', 'ERROR' or 'CRITICAL'. Matched case-insensitively. "
            "'WARN' and 'FATAL' are also accepted. Libraries log warnings and errors only, "
            "and the audit log is always written."
        ),
    )
    LOG_FORMAT: LogFormat = Field(
        default="TEXT",
        description="Format of all log messages: 'TEXT' or 'JSON'. Matched case-insensitively.",
    )

    @field_validator("LOG_LEVEL", mode="before")
    @classmethod
    def normalize_log_level(cls, value: Any) -> Any:
        """Match the log level case-insensitively and accept 'WARN' and 'FATAL'."""
        if isinstance(value, str):
            value = value.upper()
            return {"WARN": "WARNING", "FATAL": "CRITICAL"}.get(value, value)
        return value

    @field_validator("LOG_FORMAT", mode="before")
    @classmethod
    def normalize_log_format(cls, value: Any) -> Any:
        """Match the log format case-insensitively."""
        return value.upper() if isinstance(value, str) else value


def log_config() -> LogConfig:
    """Get logging configuration."""

    # Avoid loading environment variables when module is imported.
    return LogConfig()
