import pytest
from pydantic import ValidationError

from metadata_backend.conf.deployment import DeploymentConfig
from metadata_backend.conf.jwt import JWTConfig


def test_valid_deployment_config(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT", "NBIS")
    monkeypatch.setenv("ALLOW_UNSAFE", "TRUE")
    monkeypatch.setenv("ALLOW_REGISTRATION", "false")
    monkeypatch.setenv("JWT_KEY", "bW9jay1zZWNyZXQ=")

    config = DeploymentConfig()

    assert config.DEPLOYMENT == "NBIS"
    assert config.ALLOW_UNSAFE is True
    assert config.ALLOW_REGISTRATION is False


def test_invalid_deployment_config(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT", "INVALID")

    with pytest.raises(ValueError):
        DeploymentConfig()


def test_secret_not_shown_in_repr(monkeypatch):
    monkeypatch.setenv("JWT_KEY", "bW9jay1zZWNyZXQ=")  # mock-secret

    config = JWTConfig()

    assert "mock-secret" not in repr(config)
    assert "JWT_KEY=SecretStr('**********')" in repr(config)
    assert config.JWT_KEY.get_secret_value() == "mock-secret"


def test_secret_not_shown_in_validation_error(monkeypatch):
    monkeypatch.setenv("JWT_KEY", "bW9jay1zZWNyZXQ")

    with pytest.raises(ValidationError, match="JWT_KEY must be a valid base64-encoded string") as exc_info:
        JWTConfig()

    assert "bW9jay1zZWNyZXQ" not in str(exc_info.value)
