"""Tests for server module."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

from metadata_backend.server import init, main


class TestBasicFunctionsApp(unittest.TestCase):
    """Test basic functions from web app."""

    @patch("metadata_backend.server.web")
    @patch("metadata_backend.server.init")
    def test_main(self, mock_init, mock_webapp):
        """Should start the webapp."""
        main()
        mock_webapp.run_app.assert_called()


if __name__ == "__main__":
    unittest.main()


class AppTestCase(AioHTTPTestCase):
    """Async tests for web app."""

    async def get_application(self):
        """Retrieve web Application for test."""
        return await init()

    async def test_init(self):
        """Test everything works in init()."""
        server = await self.get_application()
        self.assertIs(type(server), web.Application)

    async def test_api_routes_are_set(self):
        """Test correct amount of API (no frontend) routes is set.

        routes considered to be separate are eg.:
        - /submissions
        - /submissions/{submissionId}
        - /submissions/{submissionId}/doi

        NOTE: If there's swagger or frontend folder generated in metadata_backend
        tests will see more routes

        """
        server = await self.get_application()
        self.assertIs(len(server.router.routes()), 54)

    async def test_frontend_routes_are_set(self):
        """Test correct routes are set when frontend folder exists."""
        frontend_static = "metadata_backend.server.frontend_static_files"
        with tempfile.TemporaryDirectory() as tempdir:
            temppath = Path(tempdir)
            Path(temppath / "static").mkdir()
            with patch(frontend_static, temppath):
                server = await self.get_application()
                routes = str([x for x in server.router.routes()])
                self.assertIn(f"{tempdir}/static", routes)
                self.assertIn("DynamicResource  /{path}", routes)

    async def test_response_headers(self):
        """Test response headers are set correctly in on_prepare_response."""
        resp = await self.client.request("GET", "/")
        self.assertEqual(resp.headers.get("Server", ""), "metadata")

    async def test_swagger_route_is_set(self):
        """Test correct routes are set when swagger folder exists."""
        swagger_static = "metadata_backend.server.swagger_static_path"
        with tempfile.TemporaryDirectory() as tempdir:
            temppath = Path(tempdir)
            Path(temppath / "swagger").mkdir()
            open(temppath / "swagger" / "index.html", "w").write("<html></html>")
            with patch(swagger_static, temppath / "swagger" / "index.html"):
                server = await self.get_application()
                routes = str([x for x in server.router.routes()])
                self.assertIn("/swagger", routes)
                self.assertIn("PlainResource  /swagger", routes)
