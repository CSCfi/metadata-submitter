"""Test api endpoints from views module."""

from pathlib import Path
from unittest.mock import patch

from aiohttp import FormData
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from bson import json_util

from metadata_backend.server import init


class SiteHandlerTestCase(AioHTTPTestCase):
    """Api endpoint class test cases."""

    TESTFILES_ROOT = Path(__file__).parent.parent / 'test_files'

    async def get_application(self):
        """Retrieve web Application for test."""
        return await init()

    async def setUpAsync(self):
        """Configure default values for testing and other modules.

        THis patches used modules and sets default return values for their
        methods. Also sets up reusable test variables for different test
        methods.
        """
        self.test_ega_string = "EGA123456"
        self.query_accessionId = "EDAG3991701442770179",
        self.metadata_json = json_util.dumps([
            {
                "_id": {
                    "$oid": "5ecd28877f55c72e263f45c2"
                },
                "study": {
                    "attributes": {
                        "centerName": "GEO",
                        "alias": "GSE10966",
                        "accession": "SRP000539"
                    },
                    "accessionId": "EDAG3991701442770179",
                    "publishDate": {
                        "$date": 1595784759233
                    }
                }
            }])
        path_to_xml_file = self.TESTFILES_ROOT / "study" / "SRP000539.xml"
        self.metadata_xml = path_to_xml_file.read_text()

        class_parser = "metadata_backend.api.views.SubmissionXMLToJSONParser"
        class_translator = "metadata_backend.api.views.ActionToCRUDTranslator"
        translator_config = {'add.return_value': self.test_ega_string,
                             'get_object_with_accessionId.side_effect':
                             self.fake_translator_get_object_with_accessionId}
        self.patch_parser = patch(class_parser, spec=True)
        self.patch_translator = patch(class_translator, **translator_config,
                                      spec=True)
        self.MockedParser = self.patch_parser.start()
        self.MockedTranslator = self.patch_translator.start()

    async def tearDownAsync(self):
        """Cleanup mocked stuff."""
        self.patch_parser.stop()
        self.patch_translator.stop()

    def create_submission_data(self, files):
        """Create request data from pairs of schemas and filenames."""
        data = FormData()
        for schema, filename in files:
            path_to_file = self.TESTFILES_ROOT / schema / filename
            data.add_field(schema.upper(),
                           open(path_to_file.as_posix(), 'r'),
                           filename=path_to_file.name,
                           content_type='text/xml')
        return data

    def fake_translator_get_object_with_accessionId(self, schema,
                                                    accessionId,
                                                    return_xml):
        """Fakes translator modules get_object method for testing."""
        return self.metadata_xml if return_xml else self.metadata_json

    @unittest_run_loop
    async def test_submission_is_processed_and_receipt_has_correct_info(self):
        """Test that submission with SUBMISSION.xml is extracted correctly."""
        files = [("submission", "ERA521986_valid.xml")]
        data = self.create_submission_data(files)
        response = await self.client.post("/submit", data=data)
        receipt = await response.text()

        assert response.status == 201
        assert response.content_type == "text/xml"
        for schema, _ in files:
            self.assertIn(schema, receipt)

    @unittest_run_loop
    async def test_submission_fails_without_submission_xml(self):
        """Test that basic POST submission fails with no submission.xml.

        User should also be notified for missing file.
        """
        files = [("analysis", "ERZ266973.xml")]
        data = self.create_submission_data(files)
        response = await self.client.post("/submit", data=data)
        failure_text = "There must be a submission.xml file in submission."
        assert response.status == 400
        self.assertIn(failure_text, await response.text())

    @unittest_run_loop
    async def test_submission_fails_with_many_submission_xmls(self):
        """Test submission fails when there's too many submission.xml -files.

        User should be notified for submitting too many files.
        """
        files = [("submission", "ERA521986_valid.xml"),
                 ("submission", "ERA521986_valid2.xml")]
        data = self.create_submission_data(files)
        response = await self.client.post("/submit", data=data)
        failure_text = "You should submit only one submission.xml file."
        assert response.status == 400
        self.assertIn(failure_text, await response.text())

    @unittest_run_loop
    async def test_correct_object_types_are_returned(self):
        """Test api endpoint for all object types."""
        response = await self.client.get("/objects")
        response_text = await response.text()
        types = ["submission", "study", "sample", "experiment", "run",
                 "analysis", "dac", "policy", "dataset", "project"]
        for type in types:
            self.assertIn(type, response_text)

    @unittest_run_loop
    async def test_submit_object(self):
        """Test that correct submission returns accessionId."""
        files = [("study", "SRP000539.xml")]
        data = self.create_submission_data(files)
        response = await self.client.post("/object/study", data=data)
        assert response.status == 201
        self.assertIn(self.test_ega_string, await response.text())

    @unittest_run_loop
    async def test_get_object(self):
        """Test that accessionId returns correct json object."""
        url = f"/object/study/{self.query_accessionId}"
        response = await self.client.get(url)
        assert response.status == 200
        assert response.content_type == "application/json"
        self.assertEqual(self.metadata_json, await response.text())

    @unittest_run_loop
    async def test_get_object_as_xml(self):
        """Test that accessionId  with xml query returns xml object."""
        url = f"/object/study/{self.query_accessionId}"
        response = await self.client.get(f"{url}?format=xml")
        assert response.status == 200
        assert response.content_type == "text/xml"
        self.assertEqual(self.metadata_xml, await response.text())
