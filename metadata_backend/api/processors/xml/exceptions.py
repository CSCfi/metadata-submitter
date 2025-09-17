"""Xml metadata object processor."""

from typing import Sequence

from lxml.etree import _LogEntry  # noqa


class SchemaValidationException(Exception):
    """Exception containing XML Schema validation errors."""

    def __init__(self, schema_type: str, errors: Sequence[_LogEntry]) -> None:
        """
        Exception containing XML Schema validation errors.

        :param errors: Sequence or XML Schema validation errors.
        """
        self.errors: Sequence[_LogEntry] = errors
        messages: list[str] = [f"Line {err.line}: {err.message}" for err in errors]
        super().__init__(f"XML Schema validation failed for '{schema_type}':\n" + "\n".join(messages))
