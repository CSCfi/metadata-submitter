"""Test the logging configuration."""

import pytest
from pydantic import ValidationError

from metadata_backend.conf.log import LogConfig


@pytest.fixture(autouse=True)
def unset_log_env(monkeypatch) -> None:
    for name in ("LOG_LEVEL", "LOG_FORMAT"):
        monkeypatch.delenv(name, raising=False)


def test_defaults() -> None:
    config = LogConfig()

    assert config.LOG_LEVEL == "INFO"
    assert config.LOG_FORMAT == "TEXT"


def test_empty_is_default(monkeypatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "")
    monkeypatch.setenv("LOG_FORMAT", "")

    config = LogConfig()

    assert config.LOG_LEVEL == "INFO"
    assert config.LOG_FORMAT == "TEXT"


def test_json_format(monkeypatch) -> None:
    monkeypatch.setenv("LOG_FORMAT", "JSON")

    assert LogConfig().LOG_FORMAT == "JSON"


def test_invalid_format(monkeypatch) -> None:
    monkeypatch.setenv("LOG_FORMAT", "xml")

    with pytest.raises(ValidationError, match="LOG_FORMAT"):
        LogConfig()


def test_lowercase_format(monkeypatch) -> None:
    monkeypatch.setenv("LOG_FORMAT", "json")

    assert LogConfig().LOG_FORMAT == "JSON"


@pytest.mark.parametrize(
    "value, level",
    [("info", "INFO"), ("Debug", "DEBUG"), ("WARN", "WARNING"), ("warn", "WARNING"), ("FATAL", "CRITICAL")],
)
def test_level_any_case_and_aliases(monkeypatch, value: str, level: str) -> None:
    monkeypatch.setenv("LOG_LEVEL", value)
    assert LogConfig().LOG_LEVEL == level


def test_invalid_level(monkeypatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "verbose")

    with pytest.raises(ValidationError, match="LOG_LEVEL"):
        LogConfig()
