"""Logging formatting and functions for debugging."""

import copy
import json
import logging
import re
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pythonjsonlogger.core import RESERVED_ATTRS
from pythonjsonlogger.json import JsonFormatter

from ..conf.log import LogFormat, log_config

# Logging is configured when this module is imported, before anything logs.
_config = log_config()


# Every text log line starts with the time and level.
TEXT_FORMAT_PREFIX = "[{asctime}] [{levelname:8s}]"
TEXT_FORMAT = TEXT_FORMAT_PREFIX + " [{name}][{process} {processName:<12}](L:{lineno}) {funcName}: {message}"


# Every JSON log line has the level, and the time, which UtcJsonFormatter adds as 'time'.
JSON_FORMAT_PREFIX = "{levelname}"
JSON_FORMAT_ARGS: dict[str, Any] = {
    "fmt": JSON_FORMAT_PREFIX + "{name}{process}{processName}{lineno}{funcName}{message}",
    "style": "{",
    # Uvicorn adds the message with terminal colour codes as an extra field.
    "reserved_attrs": [*RESERVED_ATTRS, "color_message"],
}
AUDIT_JSON_FORMAT_ARGS: dict[str, Any] = {
    "fmt": JSON_FORMAT_PREFIX + "{message}",
    "style": "{",
    # The level is shown as 'AUDIT', which identifies an audit record, like in the text format. The
    # record's own level stays INFO.
    "static_fields": {"levelname": "AUDIT"},
}


# Control characters, such as a newline, in a text log message. A message can contain request data,
# for example a path in which uvicorn has decoded '%0A' into a newline, so a message written as it is
# could start a new line that looks like another log line, for example a forged audit line. These are
# the C0 and C1 controls, among them the terminal escape '\x9b' and the line break U+0085, and the
# line and paragraph separators U+2028 and U+2029, which some viewers also treat as line breaks.
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")


def _utc_time(record: logging.LogRecord) -> str:
    """Return the record's time in UTC as ISO 8601 with milliseconds, for example '2026-10-26T17:42:31.123Z'.

    :param record: The log record.
    :returns: The time.
    """
    # datetime rounds the float timestamp to microseconds first. Taking the milliseconds from the float
    # itself would truncate, for example, 1.001 to 1.000.
    utc = datetime.fromtimestamp(record.created, timezone.utc)
    return utc.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _escape_control_characters(text: str) -> str:
    """Escape the control characters in the text as in JSON, for example a newline as '\\n'.

    :param text: The text.
    :returns: The text without control characters.
    """
    return _CONTROL_CHARACTERS.sub(lambda match: json.dumps(match.group())[1:-1], text)


class TextFormatter(logging.Formatter):
    """Format a log record as a text line, with the time in UTC and nothing that could forge a log line.

    The message's control characters are escaped, and the lines of a traceback or stack are indented.
    """

    def formatTime(self, record: logging.LogRecord, _datefmt: str | None = None) -> str:
        """Return the record's time in UTC with milliseconds, instead of logging.Formatter's local time.

        Called by logging.Formatter.format to write {asctime}.
        """
        return _utc_time(record)

    def __init__(self, fmt: str = TEXT_FORMAT) -> None:
        """Initialize the formatter.

        :param fmt: The text format.
        """
        super().__init__(fmt, style="{")

    def formatMessage(self, record: logging.LogRecord) -> str:
        """Format the line without the exception, with the message's control characters escaped.

        Called by logging.Formatter.format. The record is copied, so that other handlers get its message as it is.

        :param record: The log record.
        :returns: The line.
        """
        record = copy.copy(record)
        record.message = _escape_control_characters(record.message)
        return super().formatMessage(record)

    def format(self, record: logging.LogRecord) -> str:
        """Format the record, with every line after the first indented and its control characters escaped.

        logging.Formatter.format writes an exception's traceback or a stack on the lines after the
        first. They can contain request data, for example in an exception's message, so they are
        indented to prevent them starting new log lines.

        :param record: The log record.
        :returns: The text, one line unless the record has an exception or stack.
        """
        first, *rest = super().format(record).split("\n")
        return "\n".join([first, *(f"    {_escape_control_characters(line)}" for line in rest)])


class UtcJsonFormatter(JsonFormatter):
    """Format a log record as a JSON line, with the time written like in the text log format."""

    def add_fields(self, log_data: dict[str, Any], record: logging.LogRecord, message_dict: dict[str, Any]) -> None:
        """Add the record's fields to the JSON line, and its time as 'time'.

        python-json-logger's own timestamp has microseconds and '+00:00' instead of 'Z'.

        :param log_data: The fields of the JSON line.
        :param record: The log record.
        :param message_dict: The message, if a dict was logged instead of a string.
        """
        super().add_fields(log_data, record, message_dict)
        log_data["time"] = _utc_time(record)


def _formatter(format_: LogFormat) -> logging.Formatter:
    """Return the formatter of the log format.

    :param format_: 'TEXT' or 'JSON'.
    :returns: The formatter.
    """
    if format_ == "JSON":
        return UtcJsonFormatter(**JSON_FORMAT_ARGS)
    return TextFormatter()


# Every log other than the audit log is written by the root logger's handler. The root logger is
# at WARNING, so libraries, uvicorn included, inherit its level and log only problems. The server
# log is at LOG_LEVEL. To debug a library, set its own logger's level, for example
# logging.getLogger("sqlalchemy.engine").setLevel(logging.DEBUG).
_handler = logging.StreamHandler()
_handler.setFormatter(_formatter(_config.LOG_FORMAT))
logging.basicConfig(handlers=[_handler], level=logging.WARNING)

LOG = logging.getLogger("server")
LOG.setLevel(_config.LOG_LEVEL)


# The fields of every audit line. A detail with one of these names is written with '_' appended,
# for example 'user_id_', so that it does not replace the field.
_AUDIT_LINE_FIELDS = {"levelname", "message", "time", "action", "user_id"}


def _audit_details(record: logging.LogRecord) -> dict[str, Any]:
    """Return the details passed to audit_event, to be written at the top level of the audit line.

    :param record: The audit record.
    :returns: The details, renamed where they would replace a field of the audit line.
    """
    details: dict[str, Any] = record.__dict__.get("details", {})
    return {f"{key}_" if key in _AUDIT_LINE_FIELDS else key: value for key, value in details.items()}


class TextAuditFormatter(TextFormatter):
    """Format an audit record as a text line with the level 'AUDIT', followed by its fields.

    A plain logging.Formatter writes only the fields named in its format string, but the details
    passed to audit_event differ from action to action. This formatter writes the action, the user,
    every detail and the message as key value pairs, for example:

        [2026-10-23T12:46:45.123Z] [AUDIT   ] action="submission.publish" user_id="user1"
        submission_id="abc" message="Submission published"

    (one line, wrapped here).

    The message can contain request data, such as a path, that may add fields, for
    example a (forged) user_id. To prevent this, message is quoted like other values,
    and written last, so that a parser that extracts a field value by field name reads
    the real one.
    """

    def __init__(self) -> None:
        """Initialize the formatter."""
        super().__init__(TEXT_FORMAT_PREFIX)

    def format(self, record: logging.LogRecord) -> str:
        """Format the audit record.

        :param record: The audit record.
        :returns: The text line.
        """
        fields = {
            "action": record.__dict__.get("action"),
            "user_id": record.__dict__.get("user_id"),
            **_audit_details(record),
            "message": record.getMessage(),
        }
        # The line shows the level 'AUDIT'. The record is copied, so that its level stays INFO.
        record = copy.copy(record)
        record.levelname = "AUDIT"
        line = super().format(record)
        for key, value in fields.items():
            line += f" {key}={json.dumps(value, default=str)}"
        return line


class JsonAuditFormatter(UtcJsonFormatter):
    """Format an audit record as a JSON line, with the details passed to audit_event at the top level."""

    def add_fields(self, log_data: dict[str, Any], record: logging.LogRecord, message_dict: dict[str, Any]) -> None:
        """Add the record's fields to the JSON line, replacing 'details' with the details themselves.

        :param log_data: The fields of the JSON line.
        :param record: The audit record.
        :param message_dict: The message, if a dict was logged instead of a string.
        """
        super().add_fields(log_data, record, message_dict)
        log_data.pop("details", None)
        log_data.update(_audit_details(record))


def _audit_formatter(format_: LogFormat) -> logging.Formatter:
    """Return the audit formatter of the log format.

    :param format_: 'TEXT' or 'JSON'.
    :returns: The formatter.
    """
    if format_ == "JSON":
        return JsonAuditFormatter(**AUDIT_JSON_FORMAT_ARGS)
    return TextAuditFormatter()


# The audit log records who did what. It is always written: its level is fixed, and it does not
# propagate to the root logger, so neither LOG_LEVEL nor the server logging configuration affects it.
# A record is marked with the level 'AUDIT', and has the record's extra fields.
AUDIT = logging.getLogger("audit")
AUDIT.setLevel(logging.INFO)
AUDIT.propagate = False
_audit_handler = logging.StreamHandler()
_audit_handler.setFormatter(_audit_formatter(_config.LOG_FORMAT))
AUDIT.addHandler(_audit_handler)


@dataclass
class AuditState:
    """What audit records of the current API request are written with."""

    # Set by the authentication middleware once the user is authenticated.
    user_id: str | None = None


# Set by the audit middleware for each API request.
audit_state: ContextVar[AuditState | None] = ContextVar("audit_state", default=None)


def audit_event(action: str, message: str, **details: Any) -> None:
    """Write an audit record of the action with the user of the current request.

    The details are passed to logging as one 'details' field, so that logging never sees their
    names, and the audit formatters write them at the top level of the audit line. A detail named
    after a field of the audit line, such as 'user_id', is written with '_' appended (see
    _AUDIT_LINE_FIELDS). Never pass tokens, API keys or other secrets as details.

    :param action: The action, for example 'submission.publish'.
    :param message: A description of the action, for example 'Submission published'.
    :param details: Further details of the action in snake_case, for example 'submission_id'.
    """
    state = audit_state.get()
    AUDIT.info(
        message,
        extra={
            "action": action,
            "user_id": state.user_id if state else None,
            "details": details,
        },
    )


class CallbackQueryFilter(logging.Filter):
    """Keep the OIDC authorization code out of the uvicorn access log.

    After login, the identity provider redirects the browser to the OIDC callback.
    Uvicorn writes every request line to its access log with the query string, so
    without this filter each login would write the user's
    authorization code and state there.

    The filter replaces the callback query with '[REDACTED]'.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Replace the OIDC callback query with '[REDACTED]' in uvicorn access log.

        :param record: An access log record.
        :returns: Always True, to log every line.
        """
        # Access log arguments: client address, method, path with query string, HTTP version, status.
        args = record.args
        if isinstance(args, tuple) and len(args) > 2 and isinstance(args[2], str):
            # The callback path is '{API_PREFIX}/callback', for example '/api/callback', so any path
            # that ends with '/callback' is treated as the callback, whatever the prefix.
            path, query_sep, _ = args[2].partition("?")
            if query_sep and path.endswith("/callback"):
                record.args = (*args[:2], f"{path}?[REDACTED]", *args[3:])
        return True


# Uvicorn writes every request line to its access log with the query string. We use a filter to
# keep the OIDC authorization code and state, sent in the login callback's query, out of the log.
# The access log is at INFO, so it is written only if uvicorn's logger level is lowered.
logging.getLogger("uvicorn.access").addFilter(CallbackQueryFilter())
