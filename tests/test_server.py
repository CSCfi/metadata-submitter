"""Tests for server module."""

import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from metadata_backend.server import init, main


class TestBasicFunctionsApp(unittest.TestCase):
    """Test basic functions from web app."""

    @patch('metadata_backend.server.web')
    @patch('metadata_backend.server.init')
    def test_main(self, mock_init, mock_webapp):
        """Should start the webapp."""
        main()
        mock_webapp.run_app.assert_called()


if __name__ == '__main__':
    unittest.main()


class AppTestCase(AioHTTPTestCase):
    """Async tests for web app."""

    async def get_application(self):
        """Retrieve web Application for test."""
        return await init()

    @unittest_run_loop
    async def test_init(self):
        """Test everything works in init()."""
        server = await self.get_application()
        self.assertIs(type(server), web.Application)

    @unittest_run_loop
    async def test_api_routes_are_set(self):
        """Test correct amount of api (no frontend) routes is set."""
        server = await self.get_application()
        for route in server.router.resources():
            print(route)
        self.assertIs(len(server.router.resources()), 5)

    @unittest_run_loop
    async def test_frontend_routes_are_set(self):
        """Test correct routes are set when frontend folder is exists."""
        frontend_static = "metadata_backend.server.frontend_static_files"
        with tempfile.TemporaryDirectory() as tempdir:
            temppath = Path(tempdir)
            Path(temppath / "static").mkdir()
            with patch(frontend_static, temppath):
                server = await self.get_application()
                routes = str([x for x in server.router.resources()])
                self.assertIn(f"{tempdir}/static", routes)
                self.assertIn("DynamicResource  /{path}", routes)
