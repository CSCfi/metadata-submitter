"""Tests for server module."""

from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError

from metadata_backend.conf.deployment import Deployment
from metadata_backend.server import main


def test_main_csc(monkeypatch):
    """Test web server main for CSC deployment."""
    monkeypatch.setenv("DEPLOYMENT", Deployment.CSC)
    monkeypatch.delenv("SERVER_PORT", raising=False)
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
    monkeypatch.setenv("DEPLOYMENT", Deployment.NBIS)
    monkeypatch.delenv("SERVER_PORT", raising=False)
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


@pytest.mark.parametrize("deployment", list(Deployment))
def test_main_server_port(monkeypatch, deployment):
    """Test that SERVER_PORT overrides the deployment's default port."""
    monkeypatch.setenv("DEPLOYMENT", deployment)
    monkeypatch.setenv("SERVER_PORT", "8080")
    monkeypatch.setenv("JWT_KEY", "bW9jay1zZWNyZXQ=")
    with (
        patch("metadata_backend.server.create_app", return_value=Mock()),
        patch("metadata_backend.server.uvicorn.run") as mock_uvicorn_run,
    ):
        main()
        assert mock_uvicorn_run.call_args.kwargs["port"] == 8080


@pytest.mark.parametrize("server_port", ["-1", "0", "65536", "port"])
def test_main_invalid_server_port(monkeypatch, server_port):
    """Test that an invalid SERVER_PORT stops the server before the database migrations are applied."""
    monkeypatch.setenv("DEPLOYMENT", Deployment.CSC)
    monkeypatch.setenv("SERVER_PORT", server_port)
    monkeypatch.setenv("JWT_KEY", "bW9jay1zZWNyZXQ=")
    monkeypatch.setenv("DATABASE_MIGRATE", "true")
    with (
        patch("metadata_backend.server.migrate_schema") as mock_migrate_schema,
        patch("metadata_backend.server.uvicorn.run") as mock_uvicorn_run,
        pytest.raises(ValidationError, match="SERVER_PORT"),
    ):
        main()
    mock_migrate_schema.assert_not_called()
    mock_uvicorn_run.assert_not_called()


@pytest.mark.parametrize("migrate", [True, False])
def test_main_migrate(monkeypatch, migrate):
    """Test that the database migrations are applied before the server starts only if enabled."""
    monkeypatch.setenv("DEPLOYMENT", Deployment.CSC)
    monkeypatch.setenv("JWT_KEY", "bW9jay1zZWNyZXQ=")
    monkeypatch.setenv("DATABASE_MIGRATE", str(migrate))
    monkeypatch.delenv("SERVER_PORT", raising=False)
    calls = Mock()
    with (
        patch("metadata_backend.server.create_app", return_value=Mock()),
        patch("metadata_backend.server.migrate_schema", calls.migrate_schema),
        patch("metadata_backend.server.uvicorn.run", calls.run),
    ):
        main()
        assert [call[0] for call in calls.mock_calls] == (["migrate_schema", "run"] if migrate else ["run"])
