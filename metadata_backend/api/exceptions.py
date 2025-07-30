"""Internal API exceptions to be converted to HTTP errors."""


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
