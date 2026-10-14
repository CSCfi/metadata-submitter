"""Metadata document processor exceptions."""

from collections.abc import Iterator
from contextlib import contextmanager

from ..exceptions import SystemException, UserException


class InvalidDocumentException(SystemException):
    """
    Exception raised when a metadata document is invalid.

    It is a system error because it may be raised by an invalid document in the database we have already accepted.
    Use invalid_documents_as_user_errors to convert these errors to users errors when documents are being submitted.
    """


@contextmanager
def invalid_documents_as_user_errors() -> Iterator[None]:
    """
    Report invalid documents as user errors when documents are being submitted.

    :raises UserException: If a submitted document is invalid.
    """
    try:
        yield
    except InvalidDocumentException as e:
        raise UserException(str(e)) from e
