"""Test api endpoints from views module."""

from pathlib import Path
from unittest.mock import patch

from aiohttp import FormData
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from metadata_backend.server import init


class SiteHandlerTestCase(AioHTTPTestCase):
    """Api endpoint class testcases."""

    TESTFILES_ROOT = Path(__file__).parent.parent / 'test_files'

    async def get_application(self):
        """Retrieve web Application for test."""
        return await init()

    async def setUpAsync(self):
        """Patch api classes that have been imported to views.py module."""
        class_parser = "metadata_backend.api.views.SubmissionXMLToJSONParser"
        class_translator = "metadata_backend.api.views.ActionToCRUDTranslator"
        patch_parser = patch(class_parser, autospec=True)
        patch_translator = patch(class_translator, autospec=True)

        self.MockedParser = patch_parser.start()
        self.MockedTranslator = patch_translator.start()
        self.addCleanup(patch_parser.stop)
        self.addCleanup(patch_translator.stop)

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

    @unittest_run_loop
    async def test_submission_is_processed_and_receipt_has_correct_info(self):
        """Test that submission with SUBMISSION.xml is extracted corretly."""
        files = [("submission", "ERA521986_valid.xml")]
        data = self.create_submission_data(files)
        response = await self.client.request("POST", "/submit", data=data)
        receipt = await response.text()

        assert response.status == 201
        for schema, _ in files:
            self.assertIn(schema, receipt)

    @unittest_run_loop
    async def test_submission_fails_without_submission_xml(self):
        """Test that basic POST submission fails with no submission.xml.

        User should also be notified for missing file.
        """
        files = [("analysis", "ERZ266973.xml")]
        data = self.create_submission_data(files)
        response = await self.client.request("POST", "/submit", data=data)
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
        response = await self.client.request("POST", "/submit", data=data)
        failure_text = "You should submit only one submission.xml file."
        assert response.status == 400
        self.assertIn(failure_text, await response.text())
