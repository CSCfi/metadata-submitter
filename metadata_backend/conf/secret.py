"""Base configuration for settings that hold a secret."""

from pydantic_settings import BaseSettings


class SecretSettings(BaseSettings):
    """Settings that hold a secret.

    A validation error leaves out the input values. Otherwise it would show every
    value given, the secret included, even when another setting failed.
    """

    model_config = {"hide_input_in_errors": True}
