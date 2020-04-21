import unittest
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from aiohttp import web, FormData
from metadata_backend.server import init, main
from unittest import mock
from pathlib import Path
from metadata_backend.logger import LOG

class TestUtilClasses(unittest.TestCase):
    """Test utility classes and their methods
    """

    def setUp(self):
        """Initialise fixtures."""
        pass

    def tearDown(self):
        """Remove setup variables."""
        pass

    def test_main(self, mock_webapp):
        """Should start the webapp."""
        main()
        mock_webapp.run_app.assert_called()

    async def test_init(self):
        """Test init type."""
        server = await init()
        self.assertIs(type(server), web.Application)


if __name__ == '__main__':
    unittest.main()
