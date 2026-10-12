"""Tests for server module."""

from unittest.mock import Mock, patch

import pytest

from metadata_backend.conf.conf import DEPLOYMENT_CSC, DEPLOYMENT_NBIS
from metadata_backend.server import main


def test_main_csc(monkeypatch):
    """Test web server main for CSC deployment."""
    monkeypatch.setenv("DEPLOYMENT", DEPLOYMENT_CSC)
    monkeypatch.setenv("JWT_KEY", "bW9jay1zZWNyZXQ=")
    with (
        patch("metadata_backend.server.create_app", return_value=Mock()) as mock_create_app,
        patch("metadata_backend.server.uvicorn.run") as mock_uvicorn_run,
    ):
        main()
        mock_create_app.assert_called_once()
        mock_uvicorn_run.assert_called_once()
        args, kwargs = mock_uvicorn_run.call_args
        assert args[0] is mock_create_app.return_value
        assert kwargs["host"] == "0.0.0.0"
        assert kwargs["port"] == 5430


def test_main_nbis(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT", DEPLOYMENT_NBIS)
    monkeypatch.setenv("JWT_KEY", "bW9jay1zZWNyZXQ=")
    """Test web server main for NBIS deployment."""
    with (
        patch("metadata_backend.server.create_app", return_value=Mock()) as mock_create_app,
        patch("metadata_backend.server.uvicorn.run") as mock_uvicorn_run,
    ):
        main()
        mock_create_app.assert_called_once()
        mock_uvicorn_run.assert_called_once()
        args, kwargs = mock_uvicorn_run.call_args
        assert args[0] is mock_create_app.return_value
        assert kwargs["host"] == "0.0.0.0"
        assert kwargs["port"] == 5431


@pytest.mark.parametrize("migrate", [True, False])
def test_main_migrate(monkeypatch, migrate):
    """Test that the database migrations are applied before the server starts only if enabled."""
    monkeypatch.setenv("DEPLOYMENT", DEPLOYMENT_CSC)
    monkeypatch.setenv("JWT_KEY", "bW9jay1zZWNyZXQ=")
    monkeypatch.setenv("DATABASE_MIGRATE", str(migrate))
    calls = Mock()
    with (
        patch("metadata_backend.server.create_app", return_value=Mock()),
        patch("metadata_backend.server.migrate_schema", calls.migrate_schema),
        patch("metadata_backend.server.uvicorn.run", calls.run),
    ):
        main()
        assert [call[0] for call in calls.mock_calls] == (["migrate_schema", "run"] if migrate else ["run"])
