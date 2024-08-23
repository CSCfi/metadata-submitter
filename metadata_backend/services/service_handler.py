"""Base class for service integrations.

It provides a http client with optional basic auth, and requests that retry automatically and come with error handling
"""

from abc import ABC, abstractmethod
from typing import Any, Optional

from aiohttp import BasicAuth, ClientSession, ClientTimeout
from aiohttp.web import HTTPError, HTTPGatewayTimeout, HTTPInternalServerError
from yarl import URL

from ..helpers.logger import LOG
from .retry import retry


class ServiceServerError(HTTPError):
    """Service server errors should produce a 502 Bad Gateway response."""

    status_code = 502


class ServiceClientError(HTTPError):
    """Service client errors should be raised unmodified."""

    def __init__(
        self,
        status_code: int,
        # difficult to pinpoint type
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """Class to raise for http client errors.

        HTTPError doesn't have a setter for status_code, so this allows setting it.

        :param status_code: Set the status code here
        """
        self.status_code = status_code
        HTTPError.__init__(self, **kwargs)


class ServiceHandler(ABC):
    """General service class handler to have similar implementation between services.

    Classes inheriting should set the service_name and base_url
    """

    service_name: str
    _http_client: Optional[ClientSession] = None

    def __init__(
        self,
        base_url: URL,
        auth: Optional[BasicAuth] = None,
        http_client_timeout: Optional[ClientTimeout] = None,
        http_client_headers: Optional[dict[str, Any]] = None,
    ) -> None:
        """Create an instance with db_client and aiohttp client attached.

        :param auth: database client instance
        """
        self.auth = auth
        self.base_url = base_url
        self.connection_check_url = base_url
        self.http_client_timeout = http_client_timeout
        self.http_client_headers = http_client_headers

    @property
    def _client(self) -> ClientSession:
        """Singleton http client, customized for the service."""
        if self._http_client is None or self._http_client.closed:
            self._http_client = ClientSession(
                auth=self.auth,
                timeout=self.http_client_timeout,
                headers=self.http_client_headers,
            )
        return self._http_client

    async def http_client_close(self) -> None:
        """Close http client."""
        if self._http_client is not None:
            await self._http_client.close()

    async def check_connection(self, timeout: int = 2) -> None:
        """Check service is reachable.

        The request should raise exceptions if it fails, and interrupt code execution.

        :param timeout: Request operations timeout
        """
        await self._request(method="HEAD", url=self.connection_check_url, timeout=timeout)

    @staticmethod
    def _process_error(error: str) -> str:
        """Override in subclass and return formatted error message."""
        return error

    @abstractmethod
    async def _healtcheck(self) -> dict[str, Any]:
        """Override in subclass and return formatted status message."""

    @retry(total_tries=5)
    async def _request(
        self,
        method: str = "GET",
        url: Optional[URL] = None,
        path: str = "",
        params: Optional[str | dict[str, Any]] = None,
        json_data: Optional[dict[str, Any] | list[dict[str, Any]]] = None,
        timeout: int = 10,
    ) -> dict[str, Any] | str:
        """Request to service REST API.

        :param method: HTTP method
        :param url: Full service url. Uses self.base_url by default
        :param path: When requesting to self.base_url, provide only the path (shortcut).
        :param params: URL parameters, must be url encoded
        :param json_data: Dict with request data
        :param timeout: Request timeout in seconds
        :returns: Response body parsed as JSON
        """
        LOG.debug(
            "%s request to: %r, path %r, params %r, request payload: %r",
            method,
            (url or self.base_url),
            path,
            params,
            json_data,
        )
        if url is None:
            url = self.base_url
            if path and path.startswith("/"):
                path = path[1:]
            if path:
                url = url / path
        try:
            async with self._client.request(
                auth=self.auth,
                method=method,
                url=url,
                params=params,
                json=json_data,
                timeout=ClientTimeout(total=timeout),
            ) as response:
                if not response.ok:
                    content = await response.text()
                    log_msg = (
                        "%s request to: %s, path %r returned: %s and content: %r",
                        method,
                        self.service_name,
                        url,
                        response.status,
                        content,
                    )
                    if content:
                        content = self._process_error(content)
                    LOG.error(log_msg)
                    raise self.make_exception(reason=content, status=response.status)

                if response.content_type.endswith("json"):
                    content = await response.json()
                else:
                    content = await response.text()
                    # We should get a JSON response in most requests.
                    if method in {"GET", "POST", "PUT", "PATCH"}:
                        message = (
                            f"{method} request to {self.service_name} '{url}' "
                            f"returned an unexpected answer: '{content}'."
                        )
                        LOG.error(message)
                        raise ServiceServerError(text=message, reason=message)

            return content

        except TimeoutError as exc:
            LOG.exception("%s request to %s %r timed out.", method, self.service_name, url)
            raise HTTPGatewayTimeout(reason=f"{self.service_name} error: Could not reach service provider.") from exc
        except HTTPError:
            # These are expected
            raise
        except Exception as exc:
            LOG.exception("%s request to %s %r raised an unexpected exception.", method, self.service_name, url)
            message = f"{self.service_name} error 502: Unexpected issue when connecting to service provider."
            raise ServiceServerError(text=message, reason=message) from exc

    def make_exception(self, reason: str, status: int) -> HTTPError:
        """Create a Client or Server exception, according to status code.

        :param reason: Error message
        :param status: HTTP status code
        :returns MetaxServerError or MetaxClientError. HTTPInternalServerError on invalid input
        """
        if status < 400:
            LOG.error("HTTP status code must be an error code, >400 received %s.", status)
            return HTTPInternalServerError(reason="Server encountered an unexpected situation.")
        reason = f"{self.service_name} error: {reason}"
        if status >= 500:
            return ServiceServerError(text=reason, reason=reason)
        return ServiceClientError(text=reason, reason=reason, status_code=status)
