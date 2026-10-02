"""Logging formatting and functions for debugging."""

import logging
import os

FORMAT = "[{asctime}][{name}][{process} {processName:<12}] [{levelname:8s}](L:{lineno}) {funcName}: {message}"
logging.basicConfig(format=FORMAT, datefmt="%Y-%m-%d %H:%M:%S", style="{")

LOG = logging.getLogger("server")
LOG.setLevel(os.getenv("LOG_LEVEL", "INFO"))


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
