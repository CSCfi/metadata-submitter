"""Internal API exceptions to be converted to HTTP errors."""

from typing import Iterable


class SystemException(Exception):
    """Exception raised for system errors that should return HTTP 500."""

    def __init__(self, message: str) -> None:
        """Initialize exception."""
        self.message = message
        super().__init__(message)


class UserException(Exception):
    """Exception raised for user errors that should return HTTP 400."""

    def __init__(self, message: str) -> None:
        """Initialize exception."""
        self.message = message
        super().__init__(message)


class NotFoundUserException(Exception):
    """Exception raised for user errors that should return HTTP 404."""

    def __init__(self, message: str) -> None:
        """Initialize exception."""
        self.message = message
        super().__init__(message)


class UserErrors(Exception):
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
