"""Test service handler."""

import pytest
from aioresponses import aioresponses
from yarl import URL

from metadata_backend.api.models.health import Health
from metadata_backend.services.service_handler import ServiceHandler


class MockService(ServiceHandler):
    pass


async def test_health_ok():
    service = MockService(
        service_name="mock", base_url=URL("http://example.com"), healthcheck_url=URL("http://example.com/health")
    )

    with aioresponses() as mocked:
        mocked.get("http://example.com/health", status=200)
        result = await service.get_health()
        assert result == Health.UP


async def test_health_down():
    service = MockService(
        service_name="mock", base_url=URL("http://example.com"), healthcheck_url=URL("http://example.com/health")
    )

    with aioresponses() as mocked:
        mocked.get("http://example.com/health", status=500)
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

    with aioresponses() as mocked:
        mocked.get("http://example.com/health", status=200)
        result = await service.get_health()
        assert result == Health.DOWN
