"""Base class for service handlers that connect to external services."""

import asyncio
import atexit
from typing import Any, Awaitable, Callable, Optional

from aiohttp import BasicAuth, ClientConnectorError, ClientResponse, ClientSession, ClientTimeout
from aiohttp.web import HTTPError, HTTPGatewayTimeout, HTTPInternalServerError
from yarl import URL

from ..api.models.health import Health
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


class ServiceHandler:
    """Base class for service handlers that connect to external services."""

    _http_client: Optional[ClientSession] = None

    def __init__(
        self,
        service_name: str,
        base_url: URL,
        *,
        auth: Optional[BasicAuth] = None,
        http_client_timeout: Optional[ClientTimeout] = None,
        http_client_headers: Optional[dict[str, Any]] = None,
        healthcheck_url: URL,
        healthcheck_timeout: int = 10,
        healthcheck_callback: Callable[[ClientResponse], Awaitable[bool]] | None = None,
    ) -> None:
        """Base class for external service integrations."""

        self.service_name = service_name
        self.base_url = base_url
        self.auth = auth
        self.connection_check_url = base_url
        self.http_client_timeout = http_client_timeout
        self.http_client_headers = http_client_headers
        self.healthcheck_url = healthcheck_url
        self.healthcheck_timeout = healthcheck_timeout
        self.healthcheck_callback = healthcheck_callback

    @property
    def _client(self) -> ClientSession:
        """Singleton http client, customized for the service."""
        if self._http_client is None or self._http_client.closed:
            self._http_client = ClientSession(
                auth=self.auth,
                timeout=self.http_client_timeout,
                headers=self.http_client_headers,
            )

            # Automatically close.
            atexit.register(lambda: asyncio.run(self.close()))

        return self._http_client

    async def close(self) -> None:
        """Close http client."""
        if self._http_client is not None:
            await self._http_client.close()

    @staticmethod
    def _process_error(error: str) -> str:
        """Override in subclass and return formatted error message."""
        return error

    @retry(total_tries=5)
    async def _request(
        self,
        *,
        method: str = "GET",
        url: Optional[URL] = None,
        path: str = "",
        params: Optional[str | dict[str, Any]] = None,
        json_data: Optional[dict[str, Any] | list[dict[str, Any]]] = None,
        timeout: int = 10,
        headers: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any] | list[dict[str, Any]] | str:
        """Request to service REST API.

        :param method: HTTP method
        :param url: Full service url. Uses self.base_url by default
        :param path: When requesting to self.base_url, provide only the path (shortcut).
        :param params: URL parameters, must be url encoded
        :param json_data: Dict with request data
        :param timeout: Request timeout in seconds
        :param headers: request headers
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
                headers=headers,
            ) as response:
                if not response.ok:
                    content = await response.text()
                    log_msg = (
                        f"{method} request to: {self.service_name}, path {url} returned: "
                        f"{response.status} and content: {content}"
                    )
                    if content:
                        content = self._process_error(content)
                    LOG.error(log_msg)
                    raise self.make_exception(reason=content, status=response.status)

                if response.content_type.endswith("json"):
                    content = await response.json()
                else:
                    content = await response.text()

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
        :returns: ServiceServerError or ServiceClientError or HTTPInternalServerError on invalid input
        """
        if status < 400:
            LOG.error("HTTP status code must be an error code, received <400: %s.", status)
            return HTTPInternalServerError(reason="Server encountered an unexpected situation.")
        reason = f"{self.service_name} error: {reason}"
        if status >= 500:
            return ServiceServerError(text=reason, reason=reason)
        return ServiceClientError(text=reason, reason=reason, status_code=status)

    async def get_health(self) -> Health:
        """
        Get service health using the service handler healthcheck URL.

        :returns: The service handler health.
        """
        try:
            async with self._client.get(
                self.healthcheck_url, timeout=ClientTimeout(total=self.healthcheck_timeout)
            ) as resp:
                if resp.status != 200:
                    LOG.error("Health check failed for service '%s', url=%s", self.service_name, self.healthcheck_url)
                    return Health.DOWN

                if self.healthcheck_callback and not await self.healthcheck_callback(resp):
                    LOG.error(
                        "Health check callback failed for service '%s', url=%s", self.service_name, self.healthcheck_url
                    )
                    return Health.DOWN

                return Health.UP
        except asyncio.TimeoutError:
            LOG.warning(
                "Health check timed out for service '%s', url=%s",
                self.service_name,
                self.healthcheck_url,
            )
            return Health.DEGRADED
        except ClientConnectorError:
            LOG.error("Health check failed for service '%s', url=%s", self.service_name, self.healthcheck_url)
            return Health.DOWN
        except Exception:
            LOG.exception(
                "Unexpected error during health check for service '%s', url=%s", self.service_name, self.healthcheck_url
            )
            return Health.ERROR
