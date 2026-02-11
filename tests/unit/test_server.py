"""Tests for server module."""

from unittest.mock import Mock, patch

from metadata_backend.conf.conf import DEPLOYMENT_CSC, DEPLOYMENT_NBIS
from metadata_backend.server import main


def test_main_csc(monkeypatch):
    """Test web server main for CSC deployment."""
    monkeypatch.setenv("DEPLOYMENT", DEPLOYMENT_CSC)
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
