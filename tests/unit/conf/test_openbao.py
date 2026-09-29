"""Test the OpenBao configuration."""

import pytest
from pydantic import ValidationError

from metadata_backend.conf.openbao import DIRECT, ENVELOPE, ObjectEncryption, OpenBaoConfig


@pytest.fixture(autouse=True)
def unset_openbao_env(monkeypatch) -> None:
    for name in (
        "OPENBAO_URL",
        "OPENBAO_TOKEN",
        "OPENBAO_KUBERNETES_ROLE",
        "OPENBAO_KUBERNETES_MOUNT",
        "OPENBAO_OBJECT_KEY_NAME",
        "OPENBAO_OBJECT_ENCRYPTION",
    ):
        monkeypatch.delenv(name, raising=False)


def test_no_url() -> None:
    config = OpenBaoConfig()

    assert config.OPENBAO_URL is None
    assert config.OPENBAO_OBJECT_KEY_NAME is None
    assert config.OPENBAO_TOKEN is None


def test_url_and_key(monkeypatch) -> None:
    monkeypatch.setenv("OPENBAO_URL", "http://openbao:8200")
    monkeypatch.setenv("OPENBAO_TOKEN", "token")
    monkeypatch.setenv("OPENBAO_OBJECT_KEY_NAME", "test-key")

    config = OpenBaoConfig()

    assert config.OPENBAO_URL == "http://openbao:8200"
    assert config.OPENBAO_TOKEN == "token"
    assert config.OPENBAO_OBJECT_KEY_NAME == "test-key"
    # An envelope is the default.
    assert config.OPENBAO_OBJECT_ENCRYPTION == ENVELOPE


def test_url_no_key(monkeypatch) -> None:
    monkeypatch.setenv("OPENBAO_URL", "http://openbao:8200")

    with pytest.raises(ValidationError, match="OPENBAO_OBJECT_KEY_NAME is required"):
        OpenBaoConfig()


@pytest.mark.parametrize("encryption", [ENVELOPE, DIRECT])
def test_object_encryption(monkeypatch, encryption: ObjectEncryption) -> None:
    monkeypatch.setenv("OPENBAO_URL", "http://openbao:8200")
    monkeypatch.setenv("OPENBAO_OBJECT_KEY_NAME", "test-key")
    monkeypatch.setenv("OPENBAO_TOKEN", "test-token")
    monkeypatch.setenv("OPENBAO_OBJECT_ENCRYPTION", encryption)

    assert OpenBaoConfig().OPENBAO_OBJECT_ENCRYPTION == encryption


def test_invalid_object_encryption(monkeypatch) -> None:
    monkeypatch.setenv("OPENBAO_URL", "http://openbao:8200")
    monkeypatch.setenv("OPENBAO_OBJECT_KEY_NAME", "test-key")
    monkeypatch.setenv("OPENBAO_TOKEN", "test-token")
    monkeypatch.setenv("OPENBAO_OBJECT_ENCRYPTION", "invalid")

    with pytest.raises(ValidationError):
        OpenBaoConfig()


def test_kubernetes_role(monkeypatch) -> None:
    monkeypatch.setenv("OPENBAO_URL", "http://openbao:8200")
    monkeypatch.setenv("OPENBAO_OBJECT_KEY_NAME", "test-key")
    monkeypatch.setenv("OPENBAO_KUBERNETES_ROLE", "sd-submit")

    config = OpenBaoConfig()

    assert config.OPENBAO_KUBERNETES_ROLE == "sd-submit"
    assert config.OPENBAO_KUBERNETES_MOUNT == "kubernetes"


@pytest.mark.parametrize(
    "authentication",
    [
        {},  # Neither a token nor a role.
        {"OPENBAO_TOKEN": "test-token", "OPENBAO_KUBERNETES_ROLE": "sd-submit"},  # Both.
    ],
)
def test_authentication_method(monkeypatch, authentication: dict[str, str]) -> None:
    monkeypatch.setenv("OPENBAO_URL", "http://openbao:8200")
    monkeypatch.setenv("OPENBAO_OBJECT_KEY_NAME", "test-key")
    for name, value in authentication.items():
        monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError, match="Exactly one of OPENBAO_TOKEN and OPENBAO_KUBERNETES_ROLE"):
        OpenBaoConfig()
