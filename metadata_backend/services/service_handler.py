"""Base class for service handlers that connect to external services."""

import asyncio
from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable, Optional, override

import httpx
from pydantic import BaseModel, ValidationError
from starlette import status
from yarl import URL

from ..api.exceptions import ServiceHandlerSystemException
from ..api.models.health import Health
from ..helpers.logger import LOG

RETRY_MAX_COUNT = 3
RETRY_DELAY = 1
# The most characters of an external service error response that are logged.
MAX_LOGGED_ERROR_CONTENT = 500
RETRY_STATUS_CODES = frozenset({status.HTTP_408_REQUEST_TIMEOUT, status.HTTP_429_TOO_MANY_REQUESTS})


class HealthHandler(ABC):
    """Health check for external services."""

    def __init__(self, service_name: str) -> None:
        """
        Health check for external services.

        :param service_name: The service name.
        """

        self.service_name = service_name

    @abstractmethod
    async def get_health(self) -> Health:
        """
        Get service handler health.

        :returns: The service handler health.
        """


class ServiceHandler(HealthHandler):
    """Base class for service handlers that connect to external services."""

    # Shared HTTP client for health checks. AsyncClient is initialized lazily
    # to ensure it is tied to the correct FastAPI worker event loop.
    _health_http_client: httpx.AsyncClient | None = None
    _health_http_client_lock = asyncio.Lock()  # prevent async race conditions when creating client

    def __init__(
        self,
        service_name: str,
        base_url: URL,
        *,
        auth: httpx.BasicAuth | None = None,
        http_client_timeout: int | None = None,
        http_client_headers: dict[str, Any] | None = None,
        healthcheck_url: URL,
        healthcheck_callback: Callable[[httpx.Response], Awaitable[bool]] | None = None,
    ) -> None:
        """Base class for external service integrations."""

        super().__init__(service_name)

        self.base_url = base_url
        self.auth = auth
        # Service handler specific HTTP client. AsyncClient is initialized lazily
        # to ensure it is tied to the correct FastAPI worker event loop.
        self._http_client: httpx.AsyncClient | None = None
        self.http_client_timeout = http_client_timeout
        self.http_client_headers = http_client_headers
        self.healthcheck_url = healthcheck_url
        self.healthcheck_callback = healthcheck_callback

    @property
    def _client(self) -> httpx.AsyncClient:
        """
        Service handler HTTP client.

        The AsyncClient is initialized lazily to ensure it is tied to the correct
        FastAPI worker event loop.
        """
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                auth=self.auth,
                timeout=self.http_client_timeout,
                headers=self.http_client_headers,
                follow_redirects=True,
            )

        return self._http_client

    async def close(self) -> None:
        """Close service handler HTTP client."""
        if self._http_client is not None:
            await self._http_client.aclose()

    @classmethod
    async def _health_client(cls) -> httpx.AsyncClient:
        """
        Shared health check HTTP client.

        The AsyncClient is initialized lazily to ensure it is tied to the correct
        FastAPI worker event loop.
        """

        if cls._health_http_client is None:
            # Lock to prevent race conditions from several service handlers.
            async with cls._health_http_client_lock:
                if cls._health_http_client is None:
                    cls._health_http_client = httpx.AsyncClient(timeout=10)
        return cls._health_http_client

    @classmethod
    async def close_health_client(cls) -> None:
        """Close health check HTTP client."""
        if cls._health_http_client is not None:
            await cls._health_http_client.aclose()

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
        log_payload: bool = True,
    ) -> Any:
        """Request to service REST API.

        :param method: HTTP method
        :param url: Full service url. Uses self.base_url by default
        :param path: When requesting to self.base_url, provide only the path (shortcut).
        :param params: URL parameters, must be url encoded
        :param json_data: Dict with request data
        :param timeout: Request timeout in seconds
        :param headers: request headers
        :param log_payload: Is the request payload logged
        :returns: Response body parsed as JSON
        """
        LOG.debug(
            "%s request to: %r, path %r, params %r",
            method,
            (url or self.base_url),
            path,
            params,
        )
        if log_payload:
            LOG.debug("%s request payload: %r", method, json_data)
        if url is None:
            url = self.base_url
            if path and path.startswith("/"):
                path = path[1:]
            if path:
                url = url / path
        try:
            attempt = 0
            while True:
                response = await self._client.request(
                    auth=self.auth,
                    method=method,
                    url=str(url),
                    params=params,
                    json=json_data,
                    timeout=timeout,
                    headers=headers,
                )
                if response.is_success:
                    # Successful request.
                    content = (
                        response.json()
                        if response.headers.get("Content-Type", "").startswith("application/json")
                        else response.text
                    )
                    return content

                retryable = not response.is_client_error or response.status_code in RETRY_STATUS_CODES
                retry = attempt < RETRY_MAX_COUNT and retryable
                if retry:
                    # Failed request with retry attempts remaining.
                    attempt += 1
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    # Failed request with no retry attempts remaining.
                    # An error body can echo the request, such as metadata with personal data
                    # so only its start is logged.
                    content = response.text[:MAX_LOGGED_ERROR_CONTENT]
                    LOG.error(
                        "Service handler %s request to %s path %s returned: %d and content: %s",
                        method,
                        self.service_name,
                        url,
                        response.status_code,
                        content,
                    )
                    raise ServiceHandlerSystemException(self.service_name, service_status_code=response.status_code)
        except ServiceHandlerSystemException as exc:
            raise exc
        except Exception as exc:
            LOG.exception(
                f"Service handler {method} request to {self.service_name} path {url} raised an "
                f"unexpected exception: {str(exc)}"
            )
            raise ServiceHandlerSystemException(self.service_name, exc)

    def _validate_response[T: BaseModel](self, model: type[T], data: Any) -> T:
        """Validate an external service response.

        A response the model rejects is the service's fault, not the client's, so it is reported as a
        service error rather than a validation error that would list the service's fields to the client.

        :param model: The response model.
        :param data: The response body.
        :returns: The validated response.
        """
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            # The response may carry credentials, so the log omits the rejected values.
            LOG.error(
                "Service handler %s returned an invalid %s: %s",
                self.service_name,
                model.__name__,
                exc.errors(include_url=False, include_input=False),
            )
            raise ServiceHandlerSystemException(self.service_name, exc) from None

    @override
    async def get_health(self) -> Health:
        """
        Get service health using the service handler healthcheck URL.

        :returns: The service handler health.
        """
        try:
            health_client = await self._health_client()
            resp = await health_client.get(str(self.healthcheck_url))

            if resp.status_code != 200:
                LOG.error(
                    "Health check failed for service '%s', url=%s",
                    self.service_name,
                    self.healthcheck_url,
                )
                return Health.DOWN

            if self.healthcheck_callback and not await self.healthcheck_callback(resp):
                LOG.error(
                    "Health check callback failed for service '%s', url=%s",
                    self.service_name,
                    self.healthcheck_url,
                )
                return Health.DOWN

            return Health.UP

        except httpx.TimeoutException:
            LOG.warning(
                "Health check timed out for service '%s', url=%s",
                self.service_name,
                self.healthcheck_url,
            )
            return Health.DEGRADED

        except httpx.ConnectError:
            LOG.error(
                "Health check failed for service '%s', url=%s",
                self.service_name,
                self.healthcheck_url,
            )
            return Health.DOWN

        except Exception:
            LOG.exception(
                "Unexpected error during health check for service '%s', url=%s",
                self.service_name,
                self.healthcheck_url,
            )
            return Health.ERROR
