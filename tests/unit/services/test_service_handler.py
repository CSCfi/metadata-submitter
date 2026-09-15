"""Test service handler."""

import pytest
import respx
from starlette import status
from yarl import URL

from metadata_backend.api.exceptions import ServiceHandlerSystemException
from metadata_backend.api.models.health import Health
from metadata_backend.services.service_handler import RETRY_MAX_COUNT, ServiceHandler


class MockService(ServiceHandler):
    pass


async def test_health_ok():
    service = MockService(
        service_name="mock", base_url=URL("http://example.com"), healthcheck_url=URL("http://example.com/health")
    )

    with respx.mock as mock:
        mock.get("http://example.com/health").respond(status_code=200)
        result = await service.get_health()
        assert result == Health.UP


async def test_health_down():
    service = MockService(
        service_name="mock", base_url=URL("http://example.com"), healthcheck_url=URL("http://example.com/health")
    )

    with respx.mock as mock:
        mock.get("http://example.com/health").respond(status_code=500)
        result = await service.get_health()
        assert result == Health.DOWN


@pytest.mark.asyncio
async def test_health_callback_failure():
    async def callback(response):
        return False

    service = MockService(
        service_name="dummy",
        base_url=URL("http://example.com"),
        healthcheck_url=URL("http://example.com/health"),
        healthcheck_callback=callback,
    )

    with respx.mock as mock:
        mock.get("http://example.com/health").respond(status_code=200)
        result = await service.get_health()
        assert result == Health.DOWN


@pytest.mark.parametrize(
    "status_code,expected_requests",
    [
        (status.HTTP_400_BAD_REQUEST, 1),
        (status.HTTP_404_NOT_FOUND, 1),
        (status.HTTP_408_REQUEST_TIMEOUT, RETRY_MAX_COUNT + 1),
        (status.HTTP_429_TOO_MANY_REQUESTS, RETRY_MAX_COUNT + 1),
        (status.HTTP_500_INTERNAL_SERVER_ERROR, RETRY_MAX_COUNT + 1),
    ],
)
async def test_request_retries(monkeypatch, status_code: int, expected_requests: int):
    monkeypatch.setattr("metadata_backend.services.service_handler.RETRY_DELAY", 0)
    service = MockService(
        service_name="mock",
        base_url=URL("http://example.com"),
        healthcheck_url=URL("http://example.com/health"),
    )

    with respx.mock as mock:
        route = mock.get("http://example.com/thing").respond(status_code=status_code)

        with pytest.raises(ServiceHandlerSystemException):
            await service._request(method="GET", path="/thing")

        assert route.call_count == expected_requests
