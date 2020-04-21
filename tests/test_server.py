import unittest
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from aiohttp import web, FormData
from metadata_backend.server import init, main
from unittest import mock
from pathlib import Path
from metadata_backend.logger import LOG


class AppTestCase(AioHTTPTestCase):
    """Test for Web app.

    Testing web app endpoints.
    """
    TESTFILES_ROOT = Path(__file__).parent / 'test_files'

    async def get_application(self):
        """Retrieve web Application for test."""
        return await init()

    def create_submission_data(self, filename):
        """Creates submission data from given testfile. """
        path_to_file = self.TESTFILES_ROOT / filename
        data = FormData()
        data.add_field('SUBMISSION',
                       open(path_to_file.as_posix(), 'r'),
                       filename=path_to_file.name,
                       content_type='text/xml')
        return data

    @unittest_run_loop
    async def test_submission_works_correct_form_schema_and_valid_input(self):
        filename = "SUBMISSION.xml"
        headers = {'accept': '*/*'}
        data = self.create_submission_data(filename)
        response = await self.client.request("POST", "/submit",
                                             headers=headers, data=data)
        path_to_file = self.TESTFILES_ROOT / filename
        original_content = path_to_file.read_text()
        assert original_content == await response.text()
        assert 201 == response.status

    @unittest_run_loop
    async def test_submission_fails_correct_schema_and_invalid_input(self):
        headers = {'accept': '*/*'}
        filename = "invalid_SUBMISSION.xml"
        data = self.create_submission_data(filename)
        response = await self.client.request("POST", "/submit",
                                             headers=headers, data=data)

        failure_text = "XML file was not valid"
        self.assertIn(failure_text, await response.text())
        assert 400 == response.status

    @unittest_run_loop
    async def test_submission_fails_incorrect_schema(self):
        headers = {'accept': '*/*'}
        data = FormData()
        data.add_field('NULL', "", filename="", content_type='text/xml')
        response = await self.client.request("POST", "/submit",
                                             headers=headers, data=data)

        failure_text = "no xsd file for given schema"
        self.assertIn(failure_text, await response.text())
        assert 400 == response.status


class TestBasicFunctionsApp(unittest.TestCase):
    """Test App Base.

    Testing basic functions from web app.
    """

    def setUp(self):
        """Initialise fixtures."""
        pass

    def tearDown(self):
        """Remove setup variables."""
        pass

    @mock.patch('metadata_backend.server.web')
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
