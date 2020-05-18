import unittest
from unittest import mock

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from metadata_backend.server import init, main


class TestBasicFunctionsApp(unittest.TestCase):
    """Test basic functions from web app."""

    @mock.patch('metadata_backend.server.web')
    @mock.patch('metadata_backend.server.init')
    def test_main(self, mock_init, mock_webapp):
        """Should start the webapp."""
        main()
        mock_webapp.run_app.assert_called()


if __name__ == '__main__':
    unittest.main()


class AppTestCase(AioHTTPTestCase):

    async def get_application(self):
        """Retrieve web Application for test."""
        return await init()

    @unittest_run_loop
    async def test_init(self):
        """Test everything works in init()"""
        server = await self.get_application()
        self.assertIs(type(server), web.Application)
