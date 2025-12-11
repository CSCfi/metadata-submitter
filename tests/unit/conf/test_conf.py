import pytest

from metadata_backend.conf.deployment import DeploymentConfig


def test_config_defaults():
    config = DeploymentConfig()
    assert config.DEPLOYMENT == "CSC"
    assert config.ALLOW_UNSAFE is False
    assert config.ALLOW_REGISTRATION is True


def test_config_override(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT", "NBIS")
    monkeypatch.setenv("ALLOW_UNSAFE", "TRUE")
    monkeypatch.setenv("ALLOW_REGISTRATION", "false")

    config = DeploymentConfig()

    assert config.DEPLOYMENT == "NBIS"
    assert config.ALLOW_UNSAFE is True
    assert config.ALLOW_REGISTRATION is False


def test_config_invalid_value(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT", "INVALID")

    with pytest.raises(ValueError):
        DeploymentConfig()
