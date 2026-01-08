"""Tests for server module."""

import tempfile
import unittest
from pathlib import Path
from typing import override
from unittest.mock import Mock, patch

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

from metadata_backend.server import init, main


class TestBasicFunctionsApp(unittest.TestCase):
    """Test basic functions from web app."""

    @patch("metadata_backend.server.web", new_callable=Mock)
    @patch("metadata_backend.server.init", new_callable=Mock)
    def test_main(self, mock_init, mock_webapp):
        """Should start the webapp."""
        mock_webapp.run_app = Mock()
        main()
        mock_init.assert_called_once()
        mock_webapp.run_app.assert_called_once()


class AppTestCase(AioHTTPTestCase):
    """Async tests for web app."""

    @override
    async def get_application(self):
        """Create web Application."""
        return await init()

    async def test_init(self):
        """Test that the web application initializes."""
        self.assertIs(type(self.app), web.Application)
        self.assertIs(len(self.app.router.routes()), 47)

    async def test_frontend_routes_are_set(self):
        """Test correct routes are set when frontend folder exists."""
        frontend_static = "metadata_backend.server.frontend_static_files"
        with tempfile.TemporaryDirectory() as tempdir:
            temppath = Path(tempdir)
            Path(temppath / "assets").mkdir()
            with patch(frontend_static, temppath):
                server = await self.get_application()
                routes = str([x for x in server.router.routes()])
                self.assertIn(f"{tempdir}/assets", routes)
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
