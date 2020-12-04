"""Test API auth endpoints."""

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from metadata_backend.server import init


class AccessHandlerTestCase(AioHTTPTestCase):
    """Api auth class test cases."""

    async def get_application(self):
        """Retrieve web Application for test."""
        return await init()
