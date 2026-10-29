"""Test logging helpers."""

import json
import logging
import re
import sys
import time
from datetime import datetime
from typing import Any

import pytest

from metadata_backend.conf.log import log_config
from metadata_backend.helpers.logger import (
    AuditState,
    CallbackQueryFilter,
    _audit_formatter,
    _formatter,
    _utc_time,
    audit_event,
    audit_state,
)


def _log_record(logger_name: str, msg: str, *args: Any, **extra: Any) -> logging.LogRecord:
    """Create an INFO log record with message arguments and extra fields."""
    record = logging.LogRecord(logger_name, logging.INFO, __file__, 1, msg, args or None, None)
    record.__dict__.update(extra)
    return record


@pytest.mark.parametrize(
    "path, logged_path",
    [
        # The OIDC callback's code and state are not written to the access log.
        ("/callback?state=secret-state&code=secret-code", "/callback?[REDACTED]"),
        ("/api/callback?state=secret-state&code=secret-code", "/api/callback?[REDACTED]"),
        # Other request lines are logged unchanged.
        ("/v1/submissions?projectId=1001", "/v1/submissions?projectId=1001"),
    ],
)
def test_callback_query_filter(path: str, logged_path: str) -> None:
    """Test that the callback query is redacted from uvicorn's access log."""
    record = _log_record("uvicorn.access", '%s - "%s %s HTTP/%s" %d', "1.2.3.4:5", "GET", path, "1.1", 303)
    assert CallbackQueryFilter().filter(record)
    assert record.getMessage() == f'1.2.3.4:5 - "GET {logged_path} HTTP/1.1" 303'


def test_uvicorn_started_without_log_config(monkeypatch) -> None:
    """Test that uvicorn is started with no logging configuration of its own, and its access log is filtered.

    With log_config=None, uvicorn sets up no handlers, so its logs go to the root logger's handler.
    """
    from metadata_backend import server

    captured = {}
    monkeypatch.setattr(server, "create_app", lambda: None)
    monkeypatch.setattr(server.uvicorn, "run", lambda *args, **kwargs: captured.update(kwargs))
    server.main()

    assert captured["log_config"] is None
    assert any(isinstance(f, CallbackQueryFilter) for f in logging.getLogger("uvicorn.access").filters)


def test_audit_record_format(audit_records) -> None:
    """Test that an audit record is one JSON line with the level 'AUDIT' and the fields at the top level."""
    audit_event("submission.publish", "Submission published", submission_id="sub1")
    [record] = audit_records()
    assert datetime.fromisoformat(record.pop("time")).tzinfo is not None
    # The record has these fields only: every audit record is written by the audit logger, so its
    # logger and process are not written.
    assert record == {
        "levelname": "AUDIT",
        "message": "Submission published",
        "action": "submission.publish",
        # Not within a request.
        "user_id": None,
        "submission_id": "sub1",
    }


def test_audit_details_renamed_if_clashing(audit_records) -> None:
    # 'user_id' clashes, so it is written as 'user_id_'.
    audit_event("test.action", "Test action", name="test", created="now", user_id="someone")

    [record] = audit_records()
    del record["time"]
    assert record == {
        "levelname": "AUDIT",
        "message": "Test action",
        "action": "test.action",
        # The user is not replaced.
        "user_id": None,
        "user_id_": "someone",
        "name": "test",
        "created": "now",
    }


def test_log_levels() -> None:
    """Test that libraries, uvicorn included, log warnings and errors only, and the server log follows LOG_LEVEL."""
    assert logging.getLogger().level == logging.WARNING
    assert logging.getLogger("httpx").getEffectiveLevel() == logging.WARNING
    assert logging.getLogger("uvicorn.access").getEffectiveLevel() == logging.WARNING
    assert logging.getLogger("server").level == logging.getLevelName(log_config().LOG_LEVEL)


def test_audit_record_written_regardless_of_log_level(audit_records, monkeypatch) -> None:
    """Test that the audit records are written whatever LOG_LEVEL and the root logger's level are."""
    monkeypatch.setattr(logging.getLogger(), "level", logging.CRITICAL)
    monkeypatch.setattr(logging.getLogger("server"), "level", logging.CRITICAL)
    audit_event("test.action", "Test action")
    assert [r["action"] for r in audit_records()] == ["test.action"]


def test_audit_event_has_request_user(audit_records) -> None:
    """Test that an audit record has the user of the current request."""
    state = AuditState()
    token = audit_state.set(state)
    try:
        # Not authenticated yet.
        audit_event("test.before", "Before authentication")
        state.user_id = "user1"
        audit_event("test.after", "After authentication")
    finally:
        audit_state.reset(token)

    assert [r["user_id"] for r in audit_records()] == [None, "user1"]


def test_json_format() -> None:
    """Test that a log record is written as one JSON object in the JSON log format."""
    log_record = _log_record("server", "Server started")
    record = json.loads(_formatter("JSON").format(log_record))
    assert datetime.fromisoformat(record.pop("time")).tzinfo is not None
    assert record == {
        "levelname": "INFO",
        "name": "server",
        "process": log_record.process,
        "processName": log_record.processName,
        "lineno": log_record.lineno,
        "funcName": log_record.funcName,
        "message": "Server started",
    }

    # An audit record starts like every other JSON log line.
    audit_record = json.loads(_audit_formatter("JSON").format(_log_record("audit", "Submission published")))
    assert list(record)[0] == list(audit_record)[0] == "levelname"


def test_text_format() -> None:
    """Test that a log record is written as text in the text log format."""
    line = _formatter("TEXT").format(_log_record("server", "Server started"))
    assert "[server]" in line
    assert line.endswith("Server started")


def test_text_format_indents_traceback() -> None:
    """Test that the lines of a traceback cannot start like a log line.

    An exception's message can contain request data with a newline, which the traceback writes on a line
    of its own. Every line after the first is indented and its control characters escaped.
    """
    forged = "[2026-10-26T00:00:00Z] [AUDIT   ] Submission published"
    try:
        raise ValueError(f"Invalid path: /v1/x\n{forged}\r")
    except ValueError:
        log_record = _log_record("server", "Request failed")
        log_record.exc_info = sys.exc_info()

    first, *rest = _formatter("TEXT").format(log_record).split("\n")
    assert first.endswith("Request failed")
    assert rest[0] == "    Traceback (most recent call last):"
    assert f"    {forged}\\r" in rest
    assert all(line.startswith("    ") for line in rest)


def test_text_format_escapes_control_characters() -> None:
    """Test that a text log message cannot start a new line that looks like another log line.

    A request path in which uvicorn has decoded '%0A' into a newline is written with the newline
    escaped, in both the server and the audit text formats.
    """
    path = "/v1/x\n[2026-10-26T00:00:00Z] [AUDIT   ] Submission published\r\x00"
    escaped_path = "/v1/x\\n[2026-10-26T00:00:00Z] [AUDIT   ] Submission published\\r\\u0000"

    server_line = _formatter("TEXT").format(_log_record("server", "Authorization failed: path: %s", path))
    assert server_line.endswith(f"Authorization failed: path: {escaped_path}")

    log_record = _log_record("audit", f"GET {path} 401", action="http.request", user_id=None, details={})
    audit_line = _audit_formatter("TEXT").format(log_record)
    assert audit_line.endswith(f'action="http.request" user_id=null message="GET {escaped_path} 401"')

    # The record's message is not changed for other handlers.
    assert log_record.getMessage() == f"GET {path} 401"


@pytest.mark.parametrize(
    "character, escaped",
    [
        # The C1 controls, among them a terminal escape and a line break.
        ("\x80", "\\u0080"),
        ("\x85", "\\u0085"),
        ("\x9b", "\\u009b"),
        ("\x9f", "\\u009f"),
        # The line and paragraph separators, which some viewers treat as line breaks.
        ("\u2028", "\\u2028"),
        ("\u2029", "\\u2029"),
    ],
)
def test_text_format_escapes_other_line_breaks(character: str, escaped: str) -> None:
    """Test that the C1 controls and the Unicode line separators in a text log message are escaped."""
    line = _formatter("TEXT").format(_log_record("server", "path: %s", f"/v1/x{character}y"))
    assert line.endswith(f"path: /v1/x{escaped}y")
    assert len(line.splitlines()) == 1


@pytest.mark.parametrize(
    "created, time_",
    [
        (0, "1970-01-01T00:00:00.000Z"),
        (0.25, "1970-01-01T00:00:00.250Z"),
        # Stored as floats slightly below their milliseconds, which must not be truncated.
        (1.001, "1970-01-01T00:00:01.001Z"),
        (1761500551.123, "2025-10-26T17:42:31.123Z"),
        # Below a millisecond is dropped, not rounded up into the next second.
        (1761500551.9999, "2025-10-26T17:42:31.999Z"),
    ],
)
def test_utc_time(created: float, time_: str) -> None:
    """Test that the time is written in UTC as ISO 8601 with milliseconds and 'Z'."""
    record = _log_record("server", "Server started")
    record.created = created
    assert _utc_time(record) == time_


def test_format_time_in_utc(monkeypatch) -> None:
    """Test that the time of a log line is in UTC with milliseconds, whatever the local time zone."""
    monkeypatch.setenv("TZ", "Europe/Helsinki")
    time.tzset()
    try:
        record = _log_record("server", "Server started")
        record.created = 0.25
        assert _formatter("TEXT").format(record).startswith("[1970-01-01T00:00:00.250Z]")
        assert _audit_formatter("TEXT").format(record).startswith("[1970-01-01T00:00:00.250Z]")
        assert json.loads(_formatter("JSON").format(record))["time"] == "1970-01-01T00:00:00.250Z"
        assert json.loads(_audit_formatter("JSON").format(record))["time"] == "1970-01-01T00:00:00.250Z"
    finally:
        monkeypatch.undo()
        time.tzset()


def test_audit_text_format_quotes_message() -> None:
    """Test that a request path in an audit text line is quoted.

    The path has been percent-decoded, so '%20' and '%22' are a space and a quote.
    """
    path = '/v1/x action="submission.delete" user_id="admin" status=200 x="'
    record = _log_record("audit", f"DELETE {path} 404", action="http.request", user_id=None, details={})
    line = _audit_formatter("TEXT").format(record)

    message = json.dumps(f"DELETE {path} 404")
    assert line.endswith(f'] action="http.request" user_id=null message={message}')
    # The first fields of the line are the real ones.
    assert re.search(r'\saction="([^"]*)"', line).group(1) == "http.request"
    assert re.search(r"\suser_id=(\S+)", line).group(1) == "null"


def test_audit_text_format() -> None:
    """Test that an audit record is a text line with the level 'AUDIT' and its fields in the text log format."""
    record = _log_record(
        "audit",
        "Submission published",
        action="submission.publish",
        user_id=None,
        details={"path": "/v1/a b", "user_id": "someone"},
    )
    line = _audit_formatter("TEXT").format(record)
    assert line.endswith(
        '[AUDIT   ] action="submission.publish" user_id=null path="/v1/a b" user_id_="someone"'
        ' message="Submission published"'
    )
    # The record's own level is not changed.
    assert record.levelname == "INFO"

    # It starts like every other text log line, with the level 'AUDIT'. The records are given the
    # same time, so that they are not written in different milliseconds.
    server_record = _log_record("audit", "Server started", created=record.created)
    server_line = _formatter("TEXT").format(server_record)
    assert line.split(" [AUDIT   ] ")[0] == server_line.split(" [INFO    ] ")[0]
    assert "[audit]" not in line


def test_json_format_without_color_message() -> None:
    """Test that the message uvicorn adds with terminal colour codes is not written in the JSON log format."""
    line = _formatter("JSON").format(
        _log_record("uvicorn.error", "Uvicorn running", color_message="\x1b[1mUvicorn running\x1b[0m")
    )
    record = json.loads(line)
    assert record["message"] == "Uvicorn running"
    assert "color_message" not in record
