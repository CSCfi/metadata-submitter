"""Test service handler."""

import pytest
import respx
from pydantic import BaseModel
from starlette import status
from yarl import URL

from metadata_backend.api.exceptions import ServiceHandlerSystemException
from metadata_backend.api.models.health import Health
from metadata_backend.services.service_handler import MAX_LOGGED_ERROR_CONTENT, RETRY_MAX_COUNT, ServiceHandler


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


class MockResponse(BaseModel):
    secret: str


def test_validate_response(caplog):
    """Test that an invalid service response is a service error, logged without its values."""
    service = MockService(
        service_name="mock",
        base_url=URL("http://example.com"),
        healthcheck_url=URL("http://example.com/health"),
    )

    assert service._validate_response(MockResponse, {"secret": "value"}) == MockResponse(secret="value")

    with pytest.raises(ServiceHandlerSystemException) as exc_info:
        service._validate_response(MockResponse, {"secret": ["leaked-value"]})
    assert exc_info.value.status_code == status.HTTP_502_BAD_GATEWAY
    assert str(exc_info.value) == "External service error: mock"
    assert exc_info.value.__cause__ is None
    assert "MockResponse" in caplog.text
    assert "leaked-value" not in caplog.text


async def test_request_error_content_truncated(caplog):
    """Test that only the start of an external service error response is logged."""
    service = MockService(
        service_name="mock",
        base_url=URL("http://example.com"),
        healthcheck_url=URL("http://example.com/health"),
    )
    body = "a" * MAX_LOGGED_ERROR_CONTENT + "echoed-personal-data"

    with respx.mock as mock:
        mock.get("http://example.com/thing").respond(status_code=status.HTTP_400_BAD_REQUEST, text=body)
        with pytest.raises(ServiceHandlerSystemException):
            await service._request(method="GET", path="/thing")

    assert "a" * MAX_LOGGED_ERROR_CONTENT in caplog.text
    assert "echoed-personal-data" not in caplog.text
