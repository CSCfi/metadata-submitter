"""Metadata document processor exceptions."""

from ..exceptions import UserException


class InvalidDocumentException(UserException):
    """Exception raised when a submitted metadata document is invalid."""
