"""Internal API exceptions to be converted to HTTP errors."""

from abc import ABC
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Iterable

import httpx
from ldap3.core.exceptions import LDAPCommunicationError, LDAPResponseTimeoutError
from starlette import status

from ..helpers.logger import LOG


class AppException(ABC, Exception):
    """Exception raised from the application."""

    def __init__(self, message: str, status_code: int) -> None:
        """Initialize exception."""
        self.status_code = status_code
        super().__init__(message)


class SystemException(AppException):
    """Exception raised for system errors that should return HTTP 5XX."""

    def __init__(self, message: str, status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR) -> None:
        """Initialize exception."""
        super().__init__(message, status_code)


class ServiceHandlerSystemException(SystemException):
    """Exception raised for system errors that should return HTTP 502 or HTTP 504."""

    def __init__(self, service_name: str, exc: Exception | None = None, service_status_code: int | None = None) -> None:
        """Initialize exception.

        :param service_name: The external service.
        :param exc: The exception the request raised, if it raised one.
        :param service_status_code: The status code from the external service.
        """
        status_code = status.HTTP_502_BAD_GATEWAY
        if exc and isinstance(exc, httpx.TimeoutException):
            status_code = status.HTTP_504_GATEWAY_TIMEOUT
        super().__init__(f"External service error: {service_name}", status_code)
        self.service_status_code = service_status_code


class LdapSystemException(SystemException):
    """Exception raised for LDAP errors that should return HTTP 502 or HTTP 504."""

    def __init__(self, message: str, exc: Exception | None = None) -> None:
        """Initialize exception."""
        status_code = status.HTTP_502_BAD_GATEWAY
        if exc and isinstance(exc, (LDAPCommunicationError, LDAPResponseTimeoutError)):
            status_code = status.HTTP_504_GATEWAY_TIMEOUT
        super().__init__(message, status_code)


class UserException(AppException):
    """Exception raised for user errors that should return HTTP 4XX."""

    def __init__(self, message: str, status_code: int = status.HTTP_400_BAD_REQUEST) -> None:
        """Initialize exception."""
        super().__init__(message, status_code)


class NotFoundUserException(UserException):
    """Exception raised for user errors that should return HTTP 404."""

    def __init__(self, message: str) -> None:
        """Initialize exception."""
        super().__init__(message, status.HTTP_404_NOT_FOUND)


class ForbiddenUserException(UserException):
    """Exception raised for user errors that should return HTTP 403."""

    def __init__(self, message: str) -> None:
        """Initialize exception."""
        super().__init__(message, status.HTTP_403_FORBIDDEN)


class UnauthorizedUserException(UserException):
    """Exception raised for user errors that should return HTTP 401."""

    def __init__(self, message: str) -> None:
        """Initialize exception."""
        super().__init__(message, status.HTTP_401_UNAUTHORIZED)


class UserExceptions(UserException):
    """Exception raised for multiple user errors that should return HTTP 400."""

    def __init__(self, messages: Iterable[str]) -> None:
        """
        Initialize the exception.

        Args:
            messages: An iterable of error messages.
        """
        self.messages: list[str] = list(messages)
        super().__init__("; ".join(self.messages))

    def __str__(self) -> str:
        """Return all messages joined by newlines."""

        return "\n".join(self.messages)


@contextmanager
def external_service_call(message: str) -> Iterator[None]:
    """Guard a call to an external service, logging and reporting any errors.

    User errors pass through unchanged.

    Anything else is considered a system error. The actual error message is
    logged while the provided generic message is exposed to the user.

    :param message: The error message exposed to the user, appended with 'Please try again later.'.
    """

    try:
        yield
    except UserException:
        raise
    except Exception as ex:
        LOG.exception(message)
        status_code = ex.status_code if isinstance(ex, SystemException) else status.HTTP_500_INTERNAL_SERVER_ERROR
        raise SystemException(f"{message} Please try again later.", status_code) from ex
