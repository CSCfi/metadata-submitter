"""Test the Crypt4GH configuration."""

import pytest
from pydantic import ValidationError

from metadata_backend.conf.c4gh import Crypt4GHConfig


def test_no_keys(monkeypatch) -> None:
    for name in ("CRYPT4GH_PUBLIC_KEY", "CRYPT4GH_PUBLIC_KEY_URL"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValidationError, match="CRYPT4GH_PUBLIC_KEY_URL or CRYPT4GH_PUBLIC_KEY is required"):
        Crypt4GHConfig()


def test_public_key(monkeypatch) -> None:
    monkeypatch.setenv("CRYPT4GH_PUBLIC_KEY", "key")
    monkeypatch.setenv("CRYPT4GH_PUBLIC_KEY_URL", "http://keys.test/key")

    config = Crypt4GHConfig()

    assert config.CRYPT4GH_PUBLIC_KEY == "key"
    assert config.CRYPT4GH_PUBLIC_KEY_URL == "http://keys.test/key"
