import unittest
from pathlib import Path
from unittest import mock

from aiohttp import FormData, web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from metadata_backend.server import init, main


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

    def mocked_create(self, dbservice, collection, data):
        # TODO: Fix method to respond with result object similar to
        # mondodb return (after code itself has been fixed)
        return "Mocked string response"

    def mocked_init(self):
        self.submission_db_service = mock.Mock()
        self.schema_db_service = mock.Mock()
        self.backup_db_service = mock.Mock()

    @unittest_run_loop
    @mock.patch("api.views.SiteHandler.__init__")
    @mock.patch("database.db_services.CRUDService.create")
    async def submit_works_correct_schema_valid_input(self,
                                                           mocked_sitehandler,
                                                           mocked_crudservice):
        """
        Test that submission is created correctly through /submit-endpoint.
        Test mocks database connection objects and CRUDservice that are
        normally used to talk with the database.
        """

        filename = "SUBMISSION.xml"
        headers = {'accept': '*/*'}
        data = self.create_submission_data(filename)
        mocked_sitehandler.side_effect = self.mocked_init
        mocked_crudservice.side_effect = self.mocked_create
        response = await self.client.request("POST", "/submit",
                                             headers=headers, data=data)
        path_to_file = self.TESTFILES_ROOT / filename
        original_content = path_to_file.read_text()
        assert original_content == await response.text()
        assert 201 == response.status

    @unittest_run_loop
    async def test_submit_fails_correct_schema_invalid_input(self):
        headers = {'accept': '*/*'}
        filename = "invalid_SUBMISSION.xml"
        data = self.create_submission_data(filename)
        response = await self.client.request("POST", "/submit",
                                             headers=headers, data=data)

        failure_text = "XML file was not valid"
        self.assertIn(failure_text, await response.text())
        assert 400 == response.status

    @unittest_run_loop
    async def test_submit_fails_incorrect_schema(self):
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
