import unittest

from unittest.mock import patch
from aiohttp import FormData
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from metadata_backend.server import init
from pathlib import Path
from typing import List, Dict


class SiteHandlerTestCase(AioHTTPTestCase):

    TESTFILES_ROOT = Path(__file__).parent.parent / 'test_files'

    async def get_application(self):
        """Retrieve web Application for test."""
        return await init()

    async def setUpAsync(self):
        """Patch api classes that have been imported to views.py module.

        Aiohttp response needs correct body (not just MagicMock-object), so
        receipt generating function needs to be mocked here as well.
        """
        class_parser = "metadata_backend.api.views.SubmissionXMLToJSONParser"
        class_translator = "metadata_backend.api.views.ActionToCRUDTranslator"
        patch_parser = patch(class_parser)
        patch_translator = patch(class_translator)
        self.MockedParser = patch_parser.start()
        self.MockedTranslator = patch_translator.start()
        self.addCleanup(patch_parser.stop)
        self.addCleanup(patch_translator.stop)

    def create_submission_data(self, files: List) -> Dict:
        """Creates request data from pairs of schemas and filenames."""
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
        files = []
        files.append(("submission", "ERA521986.xml"))
        data = self.create_submission_data(files)
        response = await self.client.request("POST", "/submit", data=data)
        receipt = await response.text()

        assert 201 == response.status
        for schema, _ in files:
            self.assertIn(schema, receipt)

    @unittest_run_loop
    async def test_submission_fails_without_submission_xml(self):
        """User should be notified if submission doesn't contain xml-file
        about submission actions"""
        files = []
        files.append(("analysis", "ERZ266973.xml"))
        data = self.create_submission_data(files)
        response = await self.client.request("POST", "/submit", data=data)
        failure_text = "There must be a submission.xml file in submission."
        assert 400 == response.status
        self.assertIn(failure_text, await response.text())

    @unittest_run_loop
    async def test_submission_fails_with_many_submission_xmls(self):
        """User should be notified if submission contains too many xml-files"""
        files = []
        files.append(("submission", "ERA521986.xml"))
        files.append(("submission", "ERA521986_copy.xml"))
        data = self.create_submission_data(files)
        response = await self.client.request("POST", "/submit", data=data)
        failure_text = "You should submit only one submission.xml file."
        assert 400 == response.status
        self.assertIn(failure_text, await response.text())

    # TODO: write following tests: receipt contains fails and messages,
    # failures in validation with wrong schema etc or with invalid stuff
    # (especially test response statuses with blackbox testing)
    # TODO: test receipt does not contain extra messages
