"""Test API endpoints from XMLSubmissionAPIHandler."""

from metadata_backend.conf.conf import API_PREFIX

from .common import HandlersTestCase


class XMLSubmissionHandlerTestCase(HandlersTestCase):
    """Submission API endpoint class test cases."""

    async def test_validation_passes_for_valid_xml(self):
        """Test validation endpoint for valid xml."""
        with self.patch_verify_authorization:
            files = [("study", "SRP000539.xml")]
            data = self.create_submission_data(files)
            response = await self.client.post(f"{API_PREFIX}/validate", data=data)
            self.assertEqual(response.status, 200)
            self.assertEqual({"status": 200}, await response.json())

    async def test_validation_fails_bad_schema(self):
        """Test validation fails for bad schema and valid xml."""
        with self.patch_verify_authorization:
            files = [("fake", "SRP000539.xml")]
            data = self.create_submission_data(files)
            response = await self.client.post(f"{API_PREFIX}/validate", data=data)
            self.assertEqual(response.status, 404)

    async def test_validation_fails_for_invalid_xml_syntax(self):
        """Test validation endpoint for XML with bad syntax."""
        with self.patch_verify_authorization:
            files = [("study", "SRP000539_invalid.xml")]
            data = self.create_submission_data(files)
            response = await self.client.post(f"{API_PREFIX}/validate", data=data)
            resp_dict = await response.json()
            self.assertEqual(response.status, 400)
            self.assertEqual("Faulty XML file was given.", resp_dict["detail"])
            self.assertEqual("mismatched tag", resp_dict["errors"][0]["reason"])
            self.assertEqual("line 7, column 10", resp_dict["errors"][0]["position"])
            self.assertEqual("</IDENTIFIERS>", resp_dict["errors"][0]["pointer"])

    async def test_validation_fails_for_invalid_xml(self):
        """Test validation endpoint for invalid xml."""
        with self.patch_verify_authorization:
            files = [("study", "SRP000539_invalid2.xml")]
            data = self.create_submission_data(files)
            response = await self.client.post(f"{API_PREFIX}/validate", data=data)
            resp_dict = await response.json()
            self.assertEqual(response.status, 400)
            self.assertEqual("Faulty XML file was given.", resp_dict["detail"])
            self.assertIn("attribute existing_study_type='Something wrong'", resp_dict["errors"][0]["reason"])
            self.assertIn("line 11", resp_dict["errors"][0]["position"])
            self.assertEqual("/STUDY_SET/STUDY/DESCRIPTOR/STUDY_TYPE", resp_dict["errors"][0]["pointer"])

    async def test_validation_fails_for_invalid_xml_structure(self):
        """Test validation endpoint for invalid xml structure."""
        with self.patch_verify_authorization:
            files = [("study", "SRP000539_invalid3.xml")]
            data = self.create_submission_data(files)
            response = await self.client.post(f"{API_PREFIX}/validate", data=data)
            resp_dict = await response.json()
            self.assertEqual(response.status, 400)
            self.assertEqual("Faulty XML file was given.", resp_dict["detail"])
            self.assertIn(
                "Unexpected child with tag 'STUDY_LINKS'. Tag 'DESCRIPTOR' expected", resp_dict["errors"][0]["reason"]
            )
            self.assertIn("line 8", resp_dict["errors"][0]["position"])
            self.assertEqual("/STUDY_SET/STUDY/STUDY_LINKS", resp_dict["errors"][0]["pointer"])

    async def test_validation_fails_for_another_invalid_xml(self):
        """Test validation endpoint for invalid xml tags."""
        with self.patch_verify_authorization:
            files = [("study", "SRP000539_invalid4.xml")]
            data = self.create_submission_data(files)
            response = await self.client.post(f"{API_PREFIX}/validate", data=data)
            resp_dict = await response.json()
            self.assertEqual(response.status, 400)
            self.assertEqual("Faulty XML file was given.", resp_dict["detail"])
            self.assertIn("Unexpected child with tag 'BAD_ELEMENT'", resp_dict["errors"][0]["reason"])
            self.assertIn("line 34", resp_dict["errors"][0]["position"])
            self.assertEqual("/STUDY_SET/BAD_ELEMENT", resp_dict["errors"][0]["pointer"])
            self.assertIn("Unexpected child with tag 'ANOTHER_BAD_ELEMENT'", resp_dict["errors"][1]["reason"])
            self.assertIn("line 35", resp_dict["errors"][1]["position"])
            self.assertEqual("/STUDY_SET/ANOTHER_BAD_ELEMENT", resp_dict["errors"][1]["pointer"])

    async def test_validation_fails_with_too_many_files(self):
        """Test validation endpoint for too many files."""
        with self.patch_verify_authorization:
            files = [("submission", "ERA521986_valid.xml"), ("submission", "ERA521986_valid2.xml")]
            data = self.create_submission_data(files)
            response = await self.client.post(f"{API_PREFIX}/validate", data=data)
            reason = "Only one file can be sent to this endpoint at a time."
            self.assertEqual(response.status, 400)
            self.assertIn(reason, await response.text())
