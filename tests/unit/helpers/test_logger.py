"""Test logging helpers."""

import logging

import uvicorn

from metadata_backend.helpers.logger import CallbackQueryFilter


def _access_record(path: str) -> logging.LogRecord:
    """Create a log record in the format of uvicorn's access log."""
    return logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("1.2.3.4:5", "GET", path, "1.1", 303),
        None,
    )


def test_callback_query_redacted() -> None:
    """Test that the OIDC callback's code and state are not written to the access log."""
    record = _access_record("/callback?state=secret-state&code=secret-code")
    assert CallbackQueryFilter().filter(record)
    assert record.getMessage() == '1.2.3.4:5 - "GET /callback?[REDACTED] HTTP/1.1" 303'

    record = _access_record("/api/callback?state=secret-state&code=secret-code")
    assert CallbackQueryFilter().filter(record)
    assert record.getMessage() == '1.2.3.4:5 - "GET /api/callback?[REDACTED] HTTP/1.1" 303'


def test_other_query_kept() -> None:
    """Test that other request lines are logged unchanged."""
    record = _access_record("/v1/submissions?projectId=1001")
    assert CallbackQueryFilter().filter(record)
    assert "/v1/submissions?projectId=1001" in record.getMessage()


def test_filter_applies_to_uvicorn_access_log(monkeypatch) -> None:
    """Test that the server passes the filter to uvicorn's access log handler."""
    from metadata_backend import server

    captured = {}
    monkeypatch.setattr(server, "create_app", lambda: None)
    monkeypatch.setattr(server.uvicorn, "run", lambda *args, **kwargs: captured.update(kwargs))
    server.main()

    log_config = captured["log_config"]
    assert log_config["handlers"]["access"]["filters"] == ["callback_query"]
    assert log_config["filters"]["callback_query"]["()"] is CallbackQueryFilter
    # Uvicorn's default configuration is not modified.
    assert "filters" not in uvicorn.config.LOGGING_CONFIG["handlers"]["access"]
