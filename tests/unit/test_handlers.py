"""Test API endpoints from handlers module."""

import json
import os
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import ujson
from aiohttp import FormData, web
from aiohttp.test_utils import AioHTTPTestCase, make_mocked_coro
from aiohttp.web import Request

from metadata_backend.api.handlers.restapi import RESTAPIHandler
from metadata_backend.api.models import Project, User
from metadata_backend.api.services.auth import ApiKey
from metadata_backend.api.services.project import ProjectService
from metadata_backend.conf.conf import API_PREFIX
from metadata_backend.server import init


class HandlersTestCase(AioHTTPTestCase):
    """API endpoint class test cases."""

    TESTFILES_ROOT = Path(__file__).parent.parent / "test_files"

    async def get_application(self) -> web.Application:
        """Retrieve web Application for test."""
        server = await init()
        return server

    async def setUpAsync(self) -> None:
        """Configure default values for testing and other modules.

        Patches used modules and sets default return values for their
        methods. Also sets up reusable test variables for different test
        methods.
        """
        self.app = await self.get_application()
        self.server = await self.get_server(self.app)
        self.client = await self.get_client(self.server)

        # Mock user authorisation.
        self.patch_verify_authorization = patch(
            "metadata_backend.api.middlewares.verify_authorization",
            new=AsyncMock(return_value=("mock-userid", "mock-username")),
        )

        # Mock project verification.
        self.patch_verify_user_project_success = patch.object(
            ProjectService, "verify_user_project", new=AsyncMock(return_value=True)
        )
        self.patch_verify_user_project_failure = patch.object(
            ProjectService,
            "verify_user_project",
            new=AsyncMock(side_effect=web.HTTPUnauthorized(reason="Mocked unauthorized access")),
        )

        await self.client.start_server()

        self.test_ega_string = "EGA123456"
        self.query_accessionId = ("EDAG3991701442770179",)
        self.page_num = 3
        self.page_size = 50
        self.total_objects = 150
        self.metadata_json = {
            "attributes": {"centerName": "GEO", "alias": "GSE10966", "accession": "SRP000539"},
            "accessionId": "EDAG3991701442770179",
        }
        path_to_xml_file = self.TESTFILES_ROOT / "study" / "SRP000539.xml"
        self.metadata_xml = path_to_xml_file.read_text()
        self.accession_id = "EGA123456"
        self.submission_id = "FOL12345678"
        self.project_id = "1001"
        self.workflow = "FEGA"
        self.test_submission = {
            "projectId": self.project_id,
            "submissionId": self.submission_id,
            "name": "mock submission",
            "description": "test mock submission",
            "workflow": self.workflow,
            "published": False,
            "metadataObjects": [
                {"accessionId": "EDAG3991701442770179", "schema": "study"},
                {"accessionId": "EGA111", "schema": "sample"},
                {"accessionId": "EGA112", "schema": "dac"},
                {"accessionId": "EGA113", "schema": "policy"},
                {"accessionId": "EGA114", "schema": "run"},
                {"accessionId": "EGA115", "schema": "dataset"},
            ],
            "drafts": [],
            "linkedFolder": "",
            "doiInfo": {
                "creators": [
                    {
                        "givenName": "Test",
                        "familyName": "Creator",
                        "affiliation": [
                            {
                                "name": "affiliation place",
                                "schemeUri": "https://ror.org",
                                "affiliationIdentifier": "https://ror.org/test1",
                                "affiliationIdentifierScheme": "ROR",
                            }
                        ],
                    }
                ],
                "subjects": [{"subject": "999 - Other"}],
                "keywords": "test,keyword",
            },
            "files": [{"accessionId": "file1", "version": 1, "status": "added"}],
        }
        self.user_id = "USR12345678"
        self.test_user = {
            "userId": self.user_id,
            "name": "tester",
        }
        self.projected_file_example = {
            "accessionId": "file1",
            "name": "file1",
            "path": "bucketname/file1",
            "project": "project1",
            "encrypted_checksums": [
                {"type": "sha256", "value": "82E4e60e73db2e06A00a079788F7d71f75b61a4b75f28c4c9427036d6"},
                {"type": "md5", "value": "7Ac236b1a82dac89e7cf45d2b48"},
            ],
            "unencrypted_checksums": [
                {"type": "sha256", "value": "82E4e60e73db2e06A00a079788F7d71f75b61a4b75f28c4c9427036d6"},
                {"type": "md5", "value": "7Ac236b1a82dac89e7cf45d2b48"},
            ],
        }
        self._draft_doi_data = {
            "identifier": {
                "identifierType": "DOI",
                "doi": "https://doi.org/10.xxxx/yyyyy",
            },
            "types": {
                "bibtex": "misc",
                "citeproc": "collection",
                "schemaOrg": "Collection",
                "resourceTypeGeneral": "Collection",
            },
        }

        self.operator_config = {
            "read_metadata_object.side_effect": self.fake_operator_read_metadata_object,
            "create_metadata_object.side_effect": self.fake_operator_create_metadata_object,
            "delete_metadata_object.side_effect": self.fake_operator_delete_metadata_object,
            "update_metadata_object.side_effect": self.fake_operator_update_metadata_object,
            "replace_metadata_object.side_effect": self.fake_operator_replace_metadata_object,
        }
        self.xmloperator_config = {
            "read_metadata_object.side_effect": self.fake_xmloperator_read_metadata_object,
            "create_metadata_object.side_effect": self.fake_xmloperator_create_metadata_object,
            "replace_metadata_object.side_effect": self.fake_xmloperator_replace_metadata_object,
            "delete_metadata_object.side_effect": self.fake_operator_delete_metadata_object,
        }
        self.submissionoperator_config = {
            "create_submission.side_effect": self.fake_submissionoperator_create_submission,
            "read_submission.side_effect": self.fake_submissionoperator_read_submission,
            "delete_submission.side_effect": self.fake_submissionoperator_delete_submission,
            "check_object_in_submission.side_effect": self.fake_submissionoperator_check_object,
            "get_submission_field_str.side_effect": self.fake_get_submission_field_str,
        }
        self.useroperator_config = {
            "create_user.side_effect": self.fake_useroperator_create_user,
            "read_user.side_effect": self.fake_useroperator_read_user,
        }
        self.fileoperator_config = {
            "read_submission_files.side_effect": self.fake_read_submission_files,
            "check_submission_files_ready.side_effect": self.fake_check_submission_files,
        }

        RESTAPIHandler._handle_check_ownership = make_mocked_coro(True)

        def mocked_get_param(self, req: Request, name: str) -> str:
            if name == "projectId":
                return "mock-project"
            param = req.query.get(name, "")
            if param == "":
                raise web.HTTPBadRequest(reason=f"mandatory query parameter {name} is not set")
            return param

        RESTAPIHandler._get_param = mocked_get_param

    async def tearDownAsync(self):
        """Cleanup mocked stuff."""
        await self.client.close()

    def create_submission_data(self, files):
        """Create request data from pairs of schemas and filenames."""
        data = FormData()
        for schema, filename in files:
            schema_path = "study" if schema == "fake" else schema
            path_to_file = self.TESTFILES_ROOT / schema_path / filename
            # Differentiate between xml and csv
            if filename[-3:] == "xml":
                data.add_field(
                    schema.upper(),
                    open(path_to_file.as_posix(), "r"),
                    filename=path_to_file.name,
                    content_type="text/xml",
                )
            elif filename[-3:] == "csv":
                # files = {schema.upper(): open(path_to_file.as_posix(), "r")}
                data.add_field(
                    schema.upper(),
                    open(path_to_file.as_posix(), "r"),
                    filename=path_to_file.name,
                    content_type="text/csv",
                )
        return data

    def get_file_data(self, schema, filename):
        """Read file contents as plain text."""
        path_to_file = self.TESTFILES_ROOT / schema / filename
        with open(path_to_file.as_posix(), mode="r") as csv_file:
            _reader = csv_file.read()
        return _reader

    async def fake_operator_read_metadata_object(self, schema_type, accession_id):
        """Fake read operation to return mocked JSON."""
        return (self.metadata_json, "application/json")

    async def fake_xmloperator_read_metadata_object(self, schema_type, accession_id):
        """Fake read operation to return mocked xml."""
        return (self.metadata_xml, "text/xml")

    async def fake_xmloperator_create_metadata_object(self, schema_type, content):
        """Fake create operation to return mocked accessionId."""
        return [{"accessionId": self.test_ega_string}]

    async def fake_xmloperator_replace_metadata_object(self, schema_type, accession_id, content):
        """Fake replace operation to return mocked accessionId."""
        return {"accessionId": self.test_ega_string}

    async def fake_operator_create_metadata_object(self, schema_type, content):
        """Fake create operation to return mocked accessionId."""
        return {"accessionId": self.test_ega_string}

    async def fake_operator_update_metadata_object(self, schema_type, accession_id, content):
        """Fake update operation to return mocked accessionId."""
        return self.test_ega_string

    async def fake_operator_replace_metadata_object(self, schema_type, accession_id, content):
        """Fake replace operation to return mocked accessionId."""
        return {"accessionId": self.test_ega_string}

    async def fake_operator_delete_metadata_object(self, schema_type, accession_id):
        """Fake delete operation to await successful operation indicator."""
        return True

    async def fake_operator_create_datacite_info(self, schema_type, accession_id, data):
        """Fake update operation to await successful operation indicator."""
        return True

    async def fake_submissionoperator_create_submission(self, content):
        """Fake create operation to return mocked submissionId."""
        return self.submission_id

    async def fake_submissionoperator_read_submission(self, submission_id):
        """Fake read operation to return mocked submission."""
        return self.test_submission

    async def fake_submissionoperator_delete_submission(self, submission_id):
        """Fake delete submission to await nothing."""
        return None

    async def fake_submissionoperator_check_object(self, schema_type, accession_id):
        """Fake check object in submission."""
        return self.submission_id, False

    async def fake_get_submission_field_str(self, submission_id, field):
        """Fake get submission field."""
        if field == "workflow":
            return "FEGA"
        elif field == "projectId":
            return self.project_id
        return ""

    async def fake_useroperator_create_user(self, content):
        """Fake user operation to return mocked userId."""
        return self.user_id

    async def fake_useroperator_read_user(self, user_id):
        """Fake read operation to return mocked user."""
        return self.test_user

    async def fake_read_submission_files(self, submission_id, status_list):
        """Fake read submission files."""
        return [self.projected_file_example]

    async def fake_check_submission_files(self, submission_id):
        """Fake check submission files."""
        return True, []


class APIHandlerTestCase(HandlersTestCase):
    """Schema API endpoint class test cases."""

    async def test_correct_schema_types_are_returned(self):
        """Test API endpoint for all schema types."""
        with self.patch_verify_authorization:
            response = await self.client.get(f"{API_PREFIX}/schemas")
            response_text = await response.text()
            schema_titles = [
                "Submission",
                "Study",
                "Sample",
                "Experiment",
                "Run",
                "Analysis",
                "DAC",
                "Policy",
                "Dataset",
                "Project",
                "Datacite DOI schema",
                "Bigpicture Dataset",
                "Bigpicture Image",
                "Bigpicture Sample",
                "Bigpicture Staining",
                "Bigpicture Observation",
                "Bigpicture Observer",
                "Bigpicture REMS",
                "Bigpicture Organisation",
                "Bigpicture Policy",
                "Bigpicture Landing page",
            ]

            for title in schema_titles:
                self.assertIn(title, response_text)

    async def test_correct_study_schema_are_returned(self):
        """Test API endpoint for study schema types."""
        with self.patch_verify_authorization:
            response = await self.client.get(f"{API_PREFIX}/schemas/study")
            response_text = await response.text()
            self.assertIn("study", response_text)
            self.assertNotIn("submission", response_text)

    async def test_raises_invalid_schema(self):
        """Test API endpoint for study schema types."""
        with self.patch_verify_authorization:
            response = await self.client.get(f"{API_PREFIX}/schemas/something")
            self.assertEqual(response.status, 404)

    async def test_raises_not_found_schema(self):
        """Test API endpoint for study schema types."""
        with self.patch_verify_authorization:
            response = await self.client.get(f"{API_PREFIX}/schemas/project")
            self.assertEqual(response.status, 400)
            resp_json = await response.json()
            self.assertEqual(
                resp_json["detail"], "The provided schema type could not be found. Occured for JSON schema: 'project'."
            )


class XMLSubmissionHandlerTestCase(HandlersTestCase):
    """Submission API endpoint class test cases."""

    async def setUpAsync(self):
        """Configure default values for testing and other modules.

        This patches used modules and sets default return values for their
        methods.
        """
        await super().setUpAsync()
        class_parser = "metadata_backend.api.handlers.xml_submission.XMLToJSONParser"
        self.patch_parser = patch(class_parser, spec=True)
        self.MockedParser = self.patch_parser.start()

        class_xmloperator = "metadata_backend.api.handlers.xml_submission.XMLObjectOperator"
        self.patch_xmloperator = patch(class_xmloperator, **self.xmloperator_config, spec=True)
        self.MockedXMLOperator = self.patch_xmloperator.start()

    async def tearDownAsync(self):
        """Cleanup mocked stuff."""
        await super().tearDownAsync()
        self.patch_parser.stop()
        self.patch_xmloperator.stop()

    async def test_submit_endpoint_submission_does_not_fail(self):
        """Test that submission with valid SUBMISSION.xml does not fail."""
        with self.patch_verify_authorization:
            files = [("submission", "ERA521986_valid.xml")]
            data = self.create_submission_data(files)
            self.MockedParser().parse.return_value = [{"actions": {"action": []}}, data]
            response = await self.client.post(f"{API_PREFIX}/submit/FEGA", data=data)
            self.assertEqual(response.status, 200)
            self.assertEqual(response.content_type, "application/json")
            self.MockedParser().parse.assert_called_once()

    async def test_submit_endpoint_fails_without_submission_xml(self):
        """Test that basic POST submission fails with no submission.xml.

        User should also be notified for missing file.
        """
        with self.patch_verify_authorization:
            files = [("analysis", "ERZ266973.xml")]
            data = self.create_submission_data(files)
            response = await self.client.post(f"{API_PREFIX}/submit/FEGA", data=data)
            failure_text = "There must be a submission.xml file in submission."
            self.assertEqual(response.status, 400)
            self.assertIn(failure_text, await response.text())

    async def test_submit_endpoint_fails_with_many_submission_xmls(self):
        """Test submission fails when there's too many submission.xml -files.

        User should be notified for submitting too many files.
        """
        with self.patch_verify_authorization:
            files = [("submission", "ERA521986_valid.xml"), ("submission", "ERA521986_valid2.xml")]
            data = self.create_submission_data(files)
            response = await self.client.post(f"{API_PREFIX}/submit/FEGA", data=data)
            failure_text = "You should submit only one submission.xml file."
            self.assertEqual(response.status, 400)
            self.assertIn(failure_text, await response.text())

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


class ObjectHandlerTestCase(HandlersTestCase):
    """Object API endpoint class test cases."""

    async def setUpAsync(self):
        """Configure default values for testing and other modules.

        This patches used modules and sets default return values for their
        methods.
        """
        await super().setUpAsync()

        class_xmloperator = "metadata_backend.api.handlers.object.XMLObjectOperator"
        self.patch_xmloperator = patch(class_xmloperator, **self.xmloperator_config, spec=True)
        self.MockedXMLOperator = self.patch_xmloperator.start()

        class_operator = "metadata_backend.api.handlers.object.ObjectOperator"
        self.patch_operator = patch(class_operator, **self.operator_config, spec=True)
        self.MockedOperator = self.patch_operator.start()

        class_csv_parser = "metadata_backend.api.handlers.common.CSVToJSONParser"
        self.patch_csv_parser = patch(class_csv_parser, spec=True)
        self.MockedCSVParser = self.patch_csv_parser.start()

        class_submissionoperator = "metadata_backend.api.handlers.object.SubmissionOperator"
        self.patch_submissionoperator = patch(class_submissionoperator, **self.submissionoperator_config, spec=True)
        self.MockedSubmissionOperator = self.patch_submissionoperator.start()

        self._publish_handler = "metadata_backend.api.handlers.publish.PublishSubmissionAPIHandler"

    async def tearDownAsync(self):
        """Cleanup mocked stuff."""
        await super().tearDownAsync()
        self.patch_xmloperator.stop()
        self.patch_csv_parser.stop()
        self.patch_submissionoperator.stop()
        self.patch_operator.stop()

    async def test_submit_object_works(self):
        """Test that submission is handled, XMLObjectOperator is called."""
        files = [("study", "SRP000539.xml")]
        data = self.create_submission_data(files)
        with (
            patch(
                f"{self._publish_handler}.create_draft_doi",
                return_value=self._draft_doi_data,
            ),
            self.patch_verify_authorization,
        ):
            response = await self.client.post(
                f"{API_PREFIX}/objects/study", params={"submission": "some id"}, data=data
            )
            self.assertEqual(response.status, 201)
            self.assertIn(self.test_ega_string, await response.text())
            self.MockedXMLOperator().create_metadata_object.assert_called_once()

    async def test_submit_object_works_with_json(self):
        """Test that JSON submission is handled, operator is called."""
        json_req = {
            "centerName": "GEO",
            "alias": "GSE10966",
            "descriptor": {
                "studyTitle": "Highly",
                "studyType": "Other",
                "studyAbstract": "abstract description for testing",
            },
        }
        with (
            patch(
                f"{self._publish_handler}.create_draft_doi",
                return_value=self._draft_doi_data,
            ),
            self.patch_verify_authorization,
        ):
            response = await self.client.post(
                f"{API_PREFIX}/objects/study", params={"submission": "some id"}, json=json_req
            )
            self.assertEqual(response.status, 201)
            self.assertIn(self.test_ega_string, await response.text())
            self.MockedOperator().create_metadata_object.assert_called_once()

    async def test_submit_object_missing_field_json(self):
        """Test that JSON has missing property."""
        with self.patch_verify_authorization:
            json_req = {"centerName": "GEO", "alias": "GSE10966"}
            response = await self.client.post(
                f"{API_PREFIX}/objects/study", params={"submission": "some id"}, json=json_req
            )
            reason = "Provided input does not seem correct because: ''descriptor' is a required property'"
            self.assertEqual(response.status, 400)
            self.assertIn(reason, await response.text())

    async def test_submit_object_bad_field_json(self):
        """Test that JSON has bad studyType."""
        json_req = {
            "centerName": "GEO",
            "alias": "GSE10966",
            "descriptor": {
                "studyTitle": "Highly",
                "studyType": "ceva",
                "studyAbstract": "abstract description for testing",
            },
        }
        with self.patch_verify_authorization:
            response = await self.client.post(
                f"{API_PREFIX}/objects/study", params={"submission": "some id"}, json=json_req
            )
            reason = "Provided input does not seem correct for field: 'studyType'"
            self.assertEqual(response.status, 400)
            self.assertIn(reason, await response.text())

    async def test_post_object_bad_json(self):
        """Test that post JSON is badly formated."""
        json_req = {
            "centerName": "GEO",
            "alias": "GSE10966",
            "descriptor": {
                "studyTitle": "Highly",
                "studyType": "Other",
                "studyAbstract": "abstract description for testing",
            },
        }
        with self.patch_verify_authorization:
            response = await self.client.post(
                f"{API_PREFIX}/objects/study", params={"submission": "some id"}, data=json_req
            )
            reason = "JSON is not correctly formatted, err: Expecting value: line 1 column 1 (char 0)"
            self.assertEqual(response.status, 400)
            self.assertIn(reason, await response.text())

    async def test_post_object_works_with_csv(self):
        """Test that CSV file is parsed and submitted as json."""
        files = [("sample", "EGAformat.csv")]
        data = self.create_submission_data(files)
        file_content = self.get_file_data("sample", "EGAformat.csv")
        self.MockedCSVParser().parse.return_value = [{}, {}, {}]
        with self.patch_verify_authorization:
            response = await self.client.post(
                f"{API_PREFIX}/objects/sample", params={"submission": "some id"}, data=data
            )
            json_resp = await response.json()
            self.assertEqual(response.status, 201)
            self.assertEqual(self.test_ega_string, json_resp[0]["accessionId"])
            parse_calls = [
                call(
                    "sample",
                    file_content,
                )
            ]
            op_calls = [call("sample", {}), call("sample", {}), call("sample", {})]
            self.MockedCSVParser().parse.assert_has_calls(parse_calls, any_order=True)
            self.MockedOperator().create_metadata_object.assert_has_calls(op_calls, any_order=True)

    async def test_post_objet_error_with_empty(self):
        """Test multipart request post fails when no objects are parsed."""
        files = [("sample", "empty.csv")]
        data = self.create_submission_data(files)
        with self.patch_verify_authorization:
            response = await self.client.post(
                f"{API_PREFIX}/objects/sample", params={"submission": "some id"}, data=data
            )
            json_resp = await response.json()
            self.assertEqual(response.status, 400)
            self.assertEqual(json_resp["detail"], "Request data seems empty.")
            self.MockedCSVParser().parse.assert_called_once()

    async def test_put_object_bad_json(self):
        """Test that put JSON is badly formated."""
        json_req = {
            "centerName": "GEO",
            "alias": "GSE10966",
            "descriptor": {
                "studyTitle": "Highly",
                "studyType": "Other",
                "studyAbstract": "abstract description for testing",
            },
        }
        call = f"{API_PREFIX}/drafts/study/EGA123456"
        with self.patch_verify_authorization:
            response = await self.client.put(call, data=json_req)
            reason = "JSON is not correctly formatted, err: Expecting value: line 1 column 1 (char 0)"
            self.assertEqual(response.status, 400)
            self.assertIn(reason, await response.text())

    async def test_patch_object_bad_json(self):
        """Test that patch JSON is badly formated."""
        json_req = {"centerName": "GEO", "alias": "GSE10966"}
        call = f"{API_PREFIX}/drafts/study/EGA123456"
        with self.patch_verify_authorization:
            response = await self.client.patch(call, data=json_req)
            reason = "JSON is not correctly formatted, err: Expecting value: line 1 column 1 (char 0)"
            self.assertEqual(response.status, 400)
            self.assertIn(reason, await response.text())

    async def test_submit_draft_works_with_json(self):
        """Test that draft JSON submission is handled, operator is called."""
        json_req = {
            "centerName": "GEO",
            "alias": "GSE10966",
            "descriptor": {
                "studyTitle": "Highly",
                "studyType": "Other",
                "studyAbstract": "abstract description for testing",
            },
        }
        with self.patch_verify_authorization:
            response = await self.client.post(
                f"{API_PREFIX}/drafts/study", params={"submission": "some id"}, json=json_req
            )
            self.assertEqual(response.status, 201)
            self.assertIn(self.test_ega_string, await response.text())
            self.MockedOperator().create_metadata_object.assert_called_once()

    async def test_put_draft_works_with_json(self):
        """Test that draft JSON put method is handled, operator is called."""
        json_req = {
            "centerName": "GEO",
            "alias": "GSE10966",
            "descriptor": {
                "studyTitle": "Highly",
                "studyType": "Other",
                "studyAbstract": "abstract description for testing",
            },
        }
        call = f"{API_PREFIX}/drafts/study/EGA123456"
        with (self.patch_verify_authorization,):
            response = await self.client.put(call, json=json_req)
            self.assertEqual(response.status, 200)
            self.assertIn(self.test_ega_string, await response.text())
            self.MockedOperator().replace_metadata_object.assert_called_once()

    async def test_put_draft_works_with_xml(self):
        """Test that put XML submisssion is handled, XMLObjectOperator is called."""
        files = [("study", "SRP000539.xml")]
        data = self.create_submission_data(files)
        call = f"{API_PREFIX}/drafts/study/EGA123456"
        with (self.patch_verify_authorization,):
            response = await self.client.put(call, data=data)
            self.assertEqual(response.status, 200)
            self.assertIn(self.test_ega_string, await response.text())
            self.MockedXMLOperator().replace_metadata_object.assert_called_once()

    async def test_patch_draft_works_with_json(self):
        """Test that draft JSON patch method is handled, operator is called."""
        json_req = {"centerName": "GEO", "alias": "GSE10966"}
        call = f"{API_PREFIX}/drafts/study/EGA123456"
        with self.patch_verify_authorization:
            response = await self.client.patch(call, json=json_req)
            self.assertEqual(response.status, 200)
            self.assertIn(self.test_ega_string, await response.text())
            self.MockedOperator().update_metadata_object.assert_called_once()

    async def test_patch_draft_raises_with_xml(self):
        """Test that patch XML submisssion raises error."""
        with self.patch_verify_authorization:
            files = [("study", "SRP000539.xml")]
            data = self.create_submission_data(files)
            call = f"{API_PREFIX}/drafts/study/EGA123456"
            response = await self.client.patch(call, data=data)
            self.assertEqual(response.status, 415)

    async def test_submit_object_fails_with_too_many_files(self):
        """Test that sending two files to endpoint results failure."""
        with self.patch_verify_authorization:
            files = [("study", "SRP000539.xml"), ("study", "SRP000539_copy.xml")]
            data = self.create_submission_data(files)
            response = await self.client.post(
                f"{API_PREFIX}/objects/study", params={"submission": "some id"}, data=data
            )
            reason = "Only one file can be sent to this endpoint at a time."
            self.assertEqual(response.status, 400)
            self.assertIn(reason, await response.text())

    async def test_get_object(self):
        """Test that accessionId returns correct JSON object."""
        with self.patch_verify_authorization:
            url = f"{API_PREFIX}/objects/study/{self.query_accessionId}"
            response = await self.client.get(url)
            self.assertEqual(response.status, 200)
            self.assertEqual(response.content_type, "application/json")
            self.assertEqual(self.metadata_json, await response.json())

    async def test_get_draft_object(self):
        """Test that draft accessionId returns correct JSON object."""
        with self.patch_verify_authorization:
            url = f"{API_PREFIX}/drafts/study/{self.query_accessionId}"
            response = await self.client.get(url)
            self.assertEqual(response.status, 200)
            self.assertEqual(response.content_type, "application/json")
            self.assertEqual(self.metadata_json, await response.json())

    async def test_get_object_as_xml(self):
        """Test that accessionId  with XML query returns XML object."""
        url = f"{API_PREFIX}/objects/study/{self.query_accessionId}"
        with self.patch_verify_authorization:
            response = await self.client.get(f"{url}?format=xml")
            self.assertEqual(response.status, 200)
            self.assertEqual(response.content_type, "text/xml")
            self.assertEqual(self.metadata_xml, await response.text())

    async def test_delete_is_called(self):
        """Test query method calls operator and returns status correctly."""
        url = f"{API_PREFIX}/objects/study/EGA123456"
        with (
            patch(
                "metadata_backend.services.datacite_service_handler.DataciteServiceHandler.delete", return_value=None
            ),
            self.patch_verify_authorization,
        ):
            response = await self.client.delete(url)
            self.assertEqual(response.status, 204)
            self.MockedOperator().delete_metadata_object.assert_called_once()

    async def test_operations_fail_for_wrong_schema_type(self):
        """Test 404 error is raised if incorrect schema name is given."""
        with self.patch_verify_authorization:
            get_resp = await self.client.get(f"{API_PREFIX}/objects/bad_scehma_name/some_id")
            self.assertEqual(get_resp.status, 404)
            json_get_resp = await get_resp.json()
            self.assertIn("Specified schema", json_get_resp["detail"])

            get_resp = await self.client.delete(f"{API_PREFIX}/objects/bad_scehma_name/some_id")
            self.assertEqual(get_resp.status, 404)
            json_get_resp = await get_resp.json()
            self.assertIn("Specified schema", json_get_resp["detail"])

            get_resp = await self.client.delete(f"{API_PREFIX}/drafts/bad_scehma_name/some_id")
            self.assertEqual(get_resp.status, 404)
            json_get_resp = await get_resp.json()
            self.assertIn("Specified schema", json_get_resp["detail"])

    async def test_operations_fail_for_submission_only_schemas(self):
        """Test 400 error is raised if object cannot be accessed through /objects endpoints."""
        with self.patch_verify_authorization:
            get_resp = await self.client.get(f"{API_PREFIX}/objects/bprems/some_id")
            self.assertEqual(get_resp.status, 400)
            json_get_resp = await get_resp.json()
            self.assertIn("'bprems' object is a submission-only", json_get_resp["detail"])

            get_resp = await self.client.patch(f"{API_PREFIX}/objects/bprems/some_id")
            self.assertEqual(get_resp.status, 400)
            json_get_resp = await get_resp.json()
            self.assertIn("'bprems' object is a submission-only", json_get_resp["detail"])

            get_resp = await self.client.put(f"{API_PREFIX}/objects/bprems/some_id")
            self.assertEqual(get_resp.status, 400)
            json_get_resp = await get_resp.json()
            self.assertIn("'bprems' object is a submission-only", json_get_resp["detail"])

            get_resp = await self.client.delete(f"{API_PREFIX}/objects/bprems/some_id")
            self.assertEqual(get_resp.status, 400)
            json_get_resp = await get_resp.json()
            self.assertIn("'bprems' object is a submission-only", json_get_resp["detail"])


class SubmissionHandlerTestCase(HandlersTestCase):
    """Submission API endpoint class test cases."""

    async def setUpAsync(self):
        """Configure default values for testing and other modules.

        This patches used modules and sets default return values for their
        methods.
        """
        await super().setUpAsync()

        class_submissionoperator = "metadata_backend.api.handlers.submission.SubmissionOperator"
        self.patch_submissionoperator = patch(class_submissionoperator, **self.submissionoperator_config, spec=True)
        self.MockedSubmissionOperator = self.patch_submissionoperator.start()

        class_operator = "metadata_backend.api.handlers.submission.ObjectOperator"
        self.patch_operator = patch(class_operator, **self.operator_config, spec=True)
        self.MockedOperator = self.patch_operator.start()

        class_xmloperator = "metadata_backend.api.handlers.submission.XMLObjectOperator"
        self.patch_xmloperator = patch(class_xmloperator, **self.xmloperator_config, spec=True)
        self.MockedXMLOperator = self.patch_xmloperator.start()

        class_fileoperator = "metadata_backend.api.handlers.submission.FileOperator"
        self.patch_fileoperator = patch(class_fileoperator, **self.fileoperator_config, spec=True)
        self.MockedFileOperator = self.patch_fileoperator.start()

    async def tearDownAsync(self):
        """Cleanup mocked stuff."""
        await super().tearDownAsync()
        self.patch_submissionoperator.stop()
        self.patch_operator.stop()
        self.patch_xmloperator.stop()
        self.patch_fileoperator.stop()

    async def test_submission_creation_works(self):
        """Test that submission is created and submission ID returned."""
        json_req = {"name": "test", "description": "test submission", "projectId": "1000", "workflow": "FEGA"}
        self.MockedSubmissionOperator().query_submissions.return_value = ([], 0)
        with (
            self.patch_verify_authorization,
            self.patch_verify_user_project_success,
        ):
            response = await self.client.post(f"{API_PREFIX}/submissions", json=json_req)
            json_resp = await response.json()
            self.MockedSubmissionOperator().create_submission.assert_called_once()
            self.assertEqual(response.status, 201)
            self.assertEqual(json_resp["submissionId"], self.submission_id)

    async def test_submission_creation_with_missing_name_fails(self):
        """Test that submission creation fails when missing name in request."""
        json_req = {"description": "test submission", "projectId": "1000"}
        with self.patch_verify_authorization:
            response = await self.client.post(f"{API_PREFIX}/submissions", json=json_req)
            json_resp = await response.json()
            self.assertEqual(response.status, 400)
            self.assertIn("'name' is a required property", json_resp["detail"])

    async def test_submission_creation_with_missing_project_fails(self):
        """Test that submission creation fails when missing project in request."""
        json_req = {"description": "test submission", "name": "name"}
        with self.patch_verify_authorization:
            response = await self.client.post(f"{API_PREFIX}/submissions", json=json_req)
            json_resp = await response.json()
            self.assertEqual(response.status, 400)
            self.assertIn("'projectId' is a required property", json_resp["detail"])

    async def test_submission_creation_with_empty_body_fails(self):
        """Test that submission creation fails when no data in request."""
        with self.patch_verify_authorization:
            response = await self.client.post(f"{API_PREFIX}/submissions")
            json_resp = await response.json()
            self.assertEqual(response.status, 400)
            self.assertIn("JSON is not correctly formatted", json_resp["detail"])

    async def test_submission_creation_with_duplicate_name_fails(self):
        """Test that submission creation fails when duplicate name in request."""
        json_req = {"name": "test", "description": "test submission", "projectId": "1000", "workflow": "FEGA"}
        self.MockedSubmissionOperator().query_submissions.return_value = (self.test_submission, 1)
        with (
            self.patch_verify_user_project_success,
            self.patch_verify_authorization,
        ):
            response = await self.client.post(f"{API_PREFIX}/submissions", json=json_req)
            json_resp = await response.json()
            self.assertEqual(response.status, 400)
            self.assertEqual("Submission with name 'test' already exists in project 1000", json_resp["detail"])

    async def test_get_submissions_with_1_submission(self):
        """Test get_submissions() endpoint returns list with 1 submission."""
        self.MockedSubmissionOperator().query_submissions.return_value = (self.test_submission, 1)
        with (
            self.patch_verify_user_project_success,
            self.patch_verify_authorization,
        ):
            response = await self.client.get(f"{API_PREFIX}/submissions?projectId=1000")
            self.MockedSubmissionOperator().query_submissions.assert_called_once()
            self.assertEqual(response.status, 200)
            result = {
                "page": {
                    "page": 1,
                    "size": 5,
                    "totalPages": 1,
                    "totalSubmissions": 1,
                },
                "submissions": self.test_submission,
            }
            self.assertEqual(await response.json(), result)

    async def test_get_submissions_with_no_submissions(self):
        """Test get_submissions() endpoint returns empty list."""
        self.MockedSubmissionOperator().query_submissions.return_value = ([], 0)
        with (
            self.patch_verify_user_project_success,
            self.patch_verify_authorization,
        ):
            response = await self.client.get(f"{API_PREFIX}/submissions?projectId=1000")
            self.MockedSubmissionOperator().query_submissions.assert_called_once()
            self.assertEqual(response.status, 200)
            result = {
                "page": {
                    "page": 1,
                    "size": 5,
                    "totalPages": 0,
                    "totalSubmissions": 0,
                },
                "submissions": [],
            }
            self.assertEqual(await response.json(), result)

    async def test_get_submissions_with_bad_params(self):
        """Test get_submissions() with faulty pagination parameters."""
        with (
            self.patch_verify_user_project_success,
            self.patch_verify_authorization,
        ):
            response = await self.client.get(f"{API_PREFIX}/submissions?page=ayylmao&projectId=1000")
            self.assertEqual(response.status, 400)
            resp = await response.json()
            self.assertEqual(resp["detail"], "page parameter must be a number, now it is ayylmao")

            response = await self.client.get(f"{API_PREFIX}/submissions?page=1&per_page=-100&projectId=1000")
            self.assertEqual(response.status, 400)
            resp = await response.json()
            self.assertEqual(resp["detail"], "per_page parameter must be over 0")

            response = await self.client.get(f"{API_PREFIX}/submissions?published=yes&projectId=1000")
            self.assertEqual(response.status, 400)
            resp = await response.json()
            self.assertEqual(resp["detail"], "'published' parameter must be either 'true' or 'false'")

    async def test_get_submission_works(self):
        """Test submission is returned when correct submission id is given."""
        with self.patch_verify_authorization:
            response = await self.client.get(f"{API_PREFIX}/submissions/FOL12345678")
            self.assertEqual(response.status, 200)
            self.MockedSubmissionOperator().read_submission.assert_called_once()
            json_resp = await response.json()
            self.assertEqual(self.test_submission, json_resp)

    async def test_update_submission_fails_with_wrong_key(self):
        """Test that submission does not update when wrong keys are provided."""
        data = [{"op": "add", "path": f"{API_PREFIX}/objects"}]
        with self.patch_verify_authorization:
            response = await self.client.patch(f"{API_PREFIX}/submissions/FOL12345678", json=data)
            self.assertEqual(response.status, 400)
            json_resp = await response.json()
            reason = "Patch submission operation should be provided as a JSON object"
            self.assertEqual(reason, json_resp["detail"])

            data = {"doiInfo": {}}
            response = await self.client.patch(f"{API_PREFIX}/submissions/FOL12345678", json=data)
            self.assertEqual(response.status, 400)
            json_resp = await response.json()
            reason = "Patch submission operation only accept the fields 'name', or 'description'. Provided 'doiInfo'"
            self.assertEqual(reason, json_resp["detail"])

    async def test_update_submission_passes(self):
        """Test that submission would update with correct keys."""
        self.MockedSubmissionOperator().update_submission.return_value = self.submission_id
        data = {"name": "test2"}
        with self.patch_verify_authorization:
            response = await self.client.patch(f"{API_PREFIX}/submissions/FOL12345678", json=data)
            self.MockedSubmissionOperator().update_submission.assert_called_once()
            self.assertEqual(response.status, 200)
            json_resp = await response.json()
            self.assertEqual(json_resp["submissionId"], self.submission_id)

    async def test_submission_deletion_is_called(self):
        """Test that submission would be deleted."""
        self.MockedSubmissionOperator().read_submission.return_value = self.test_submission
        with self.patch_verify_authorization:
            response = await self.client.delete(f"{API_PREFIX}/submissions/FOL12345678")
            self.MockedSubmissionOperator().read_submission.assert_called_once()
            self.MockedSubmissionOperator().delete_submission.assert_called_once()
            self.assertEqual(response.status, 204)

    async def test_patch_submission_doi_passes_and_returns_id(self):
        """Test method for adding DOI to submission works."""
        self.MockedSubmissionOperator().update_submission.return_value = self.submission_id
        data = ujson.load(open(self.TESTFILES_ROOT / "doi" / "test_doi.json"))

        with self.patch_verify_authorization:
            response = await self.client.patch(f"{API_PREFIX}/submissions/FOL12345678/doi", json=data)
            self.assertEqual(response.status, 200)
            json_resp = await response.json()
            self.assertEqual(json_resp["submissionId"], self.submission_id)

            response = await self.client.get(f"{API_PREFIX}/submissions/{self.submission_id}")
            self.assertEqual(response.status, 200)
            json_resp = await response.json()
            self.assertIn("doiInfo", json_resp)

    async def test_patch_linked_folder_passes(self):
        """Test method for adding linked folder to submission works."""
        self.MockedSubmissionOperator().check_submission_linked_folder.return_value = False
        data = {"linkedFolder": "folderName"}
        with self.patch_verify_authorization:
            response = await self.client.patch(f"{API_PREFIX}/submissions/FOL12345678/folder", json=data)
            self.assertEqual(response.status, 204)

    async def test_patch_linked_folder_fails(self):
        """Test method for adding linked folder fails if it already exists."""
        self.MockedSubmissionOperator().check_submission_linked_folder.return_value = True
        data = {"linkedFolder": "folderName"}
        with self.patch_verify_authorization:
            response = await self.client.patch(f"{API_PREFIX}/submissions/FOL12345678/folder", json=data)
            self.assertEqual(response.status, 400)
            self.assertIn("It already has a linked folder", await response.text())

    async def test_patch_submission_rems_works(self):
        """Test method for adding rems data to submission works."""
        self.MockedSubmissionOperator().update_submission.return_value = self.submission_id
        data = ujson.load(open(self.TESTFILES_ROOT / "dac" / "dac_rems.json"))
        with (
            patch(
                "metadata_backend.services.rems_service_handler.RemsServiceHandler.validate_workflow_licenses",
                return_value=True,
            ),
            self.patch_verify_authorization,
        ):
            response = await self.client.patch(f"{API_PREFIX}/submissions/{self.submission_id}/rems", json=data)
            self.assertEqual(response.status, 200)
            json_resp = await response.json()
            self.assertEqual(json_resp["submissionId"], self.submission_id)

            response = await self.client.get(f"{API_PREFIX}/submissions/{self.submission_id}")
            self.assertEqual(response.status, 200)
            json_resp = await response.json()
            self.assertIn("rems", json_resp)

    async def test_patch_submission_rems_fails_with_missing_fields(self):
        """Test method for adding rems data to submission fails if required fields are missing."""
        self.MockedSubmissionOperator().update_submission.return_value = self.submission_id
        data = {"workflowId": 1}
        with self.patch_verify_authorization:
            response = await self.client.patch(f"{API_PREFIX}/submissions/{self.submission_id}/rems", json=data)
            self.assertEqual(response.status, 400)
            self.assertIn("REMS DAC is missing one or more of the required fields", await response.text())

    async def test_patch_submission_rems_fails_with_wrong_value_type(self):
        """Test method for adding rems data to submission fails if values have incorrect types."""
        self.MockedSubmissionOperator().update_submission.return_value = self.submission_id
        data = {"workflowId": 1, "organizationId": 1, "licenses": [1]}
        with self.patch_verify_authorization:
            response = await self.client.patch(f"{API_PREFIX}/submissions/{self.submission_id}/rems", json=data)
            self.assertEqual(response.status, 400)
            self.assertIn("Organization ID '1' must be a string.", await response.text())

    async def test_patch_submission_files_works(self):
        """Test patch method for submission files works."""
        self.MockedSubmissionOperator().read_submission.return_value = self.test_submission
        self.MockedSubmissionOperator().update_submission.return_value = self.submission_id
        data = [{"accessionId": "file123", "version": 1}]
        with self.patch_verify_authorization:
            response = await self.client.patch(f"{API_PREFIX}/submissions/{self.submission_id}/files", json=data)
            self.assertEqual(response.status, 204)

        # Test the same file can be modified
        data = [{**data[0], "status": "verified", "objectId": {"accessionId": "EGA111", "schema": "sample"}}]
        with self.patch_verify_authorization:
            response = await self.client.patch(f"{API_PREFIX}/submissions/{self.submission_id}/files", json=data)
            self.assertEqual(response.status, 204)

    async def test_patch_submission_files_fails_with_bad_json(self):
        """Test patch method for submission files fails with incorrectly formatted JSON."""
        self.MockedSubmissionOperator().update_submission.return_value = self.submission_id
        data = "[{'bad': 'json',}]"
        with self.patch_verify_authorization:
            response = await self.client.patch(f"{API_PREFIX}/submissions/{self.submission_id}/files", data=data)
            self.assertEqual(response.status, 400)
            json_resp = await response.json()
            self.assertIn("JSON is not correctly formatted", json_resp["detail"])

    async def test_patch_submission_files_fails_with_missing_fields(self):
        """Test patch method for submission files fails with missing fields."""
        self.MockedSubmissionOperator().update_submission.return_value = self.submission_id
        data = [{"accessionId": "file123"}]
        with self.patch_verify_authorization:
            response = await self.client.patch(f"{API_PREFIX}/submissions/{self.submission_id}/files", json=data)
            self.assertEqual(response.status, 400)
            json_resp = await response.json()
            self.assertIn("Each file must contain 'accessionId' and 'version'.", json_resp["detail"])

        data = [{**data[0], "version": 1, "objectId": {"accessionId": "EGA111"}}]
        with self.patch_verify_authorization:
            response = await self.client.patch(f"{API_PREFIX}/submissions/{self.submission_id}/files", json=data)
            self.assertEqual(response.status, 400)
            json_resp = await response.json()
            self.assertIn(
                "The objectId value must contain object with only 'accessionId' and 'schema' keys.", json_resp["detail"]
            )

    async def test_patch_submission_files_fails_when_file_not_found(self):
        """Test patch method for submission files fails when file is not part of the project."""
        self.MockedSubmissionOperator().update_submission.return_value = self.submission_id
        error_reason = "File 'file123' (version: '1') was not found."
        self.MockedFileOperator().read_file.side_effect = web.HTTPNotFound(reason=error_reason)
        data = [{"accessionId": "file123", "version": 1}]
        with self.patch_verify_authorization:
            response = await self.client.patch(f"{API_PREFIX}/submissions/{self.submission_id}/files", json=data)
            self.assertEqual(response.status, 404)
            json_resp = await response.json()
            self.assertIn(error_reason, json_resp["detail"])

    async def test_patch_submission_files_fails_when_metadata_object_not_found(self):
        """Test patch method for submission files fails when metadata object is not part of the submission."""
        self.MockedSubmissionOperator().read_submission.return_value = self.test_submission
        self.MockedSubmissionOperator().update_submission.return_value = self.submission_id
        data = [{"accessionId": "file123", "version": 1, "objectId": {"accessionId": "none", "schema": "sample"}}]
        with self.patch_verify_authorization:
            response = await self.client.patch(f"{API_PREFIX}/submissions/{self.submission_id}/files", json=data)
            self.assertEqual(response.status, 400)
            json_resp = await response.json()
            self.assertIn(
                "A sample object with accessionId 'none' does not exist in the submission's list of metadata objects.",
                json_resp["detail"],
            )


class PublishSubmissionHandlerTestCase(HandlersTestCase):
    """Publishing API endpoint class test cases."""

    async def setUpAsync(self):
        """Configure default values for testing and other modules.

        This patches used modules and sets default return values for their
        methods.
        """
        await super().setUpAsync()

        self._publish_handler = "metadata_backend.api.handlers.publish.PublishSubmissionAPIHandler"

        self._mock_prepare_doi = f"{self._publish_handler}._prepare_datacite_publication"

        class_submissionoperator = "metadata_backend.api.handlers.publish.SubmissionOperator"
        self.patch_submissionoperator = patch(class_submissionoperator, **self.submissionoperator_config, spec=True)
        self.MockedSubmissionOperator = self.patch_submissionoperator.start()

        class_fileoperator = "metadata_backend.api.handlers.publish.FileOperator"
        self.patch_fileoperator = patch(class_fileoperator, **self.fileoperator_config, spec=True)
        self.MockedFileOperator = self.patch_fileoperator.start()

        class_operator = "metadata_backend.api.handlers.publish.ObjectOperator"
        self.patch_operator = patch(class_operator, **self.operator_config, spec=True)
        self.MockedOperator = self.patch_operator.start()

        class_xmloperator = "metadata_backend.api.handlers.publish.XMLObjectOperator"
        self.patch_xmloperator = patch(class_xmloperator, **self.xmloperator_config, spec=True)
        self.MockedXMLOperator = self.patch_xmloperator.start()

    async def tearDownAsync(self):
        """Cleanup mocked stuff."""
        await super().tearDownAsync()
        self.patch_submissionoperator.stop()
        self.patch_fileoperator.stop()
        self.patch_operator.stop()
        self.patch_xmloperator.stop()

    async def test_submission_is_published(self):
        """Test that submission would be published and DOI would be added."""
        self.test_submission = {**self.test_submission, **{"rems": {}}}
        self.MockedSubmissionOperator().update_submission.return_value = self.submission_id
        with (
            patch(f"{self._publish_handler}.create_draft_doi", return_value=self.user_id),
            patch(
                self._mock_prepare_doi,
                return_value=(
                    {"id": "prefix/suffix-study", "data": {"attributes": {"url": "http://metax_id", "types": {}}}},
                    [{"id": "prefix/suffix-dataset", "data": {"attributes": {"url": "http://metax_id", "types": {}}}}],
                ),
            ),
            patch(f"{self._publish_handler}.create_metax_dataset", return_value=None),
            self.patch_verify_authorization,
        ):
            response = await self.client.patch(f"{API_PREFIX}/publish/FOL12345678")
            json_resp = await response.json()
            self.assertEqual(response.status, 200)
            self.assertEqual(json_resp["submissionId"], self.submission_id)


class FilesHandlerTestCase(HandlersTestCase):
    """Files API endpoint class test cases."""

    async def setUpAsync(self):
        """Configure default values for testing and other modules.

        This patches used modules and sets default return values for their
        methods.
        """
        await super().setUpAsync()

        class_fileoperator = "metadata_backend.api.handlers.files.FileOperator"
        self.patch_fileoperator = patch(class_fileoperator, **self.fileoperator_config, spec=True)
        self.MockedFileOperator = self.patch_fileoperator.start()

        self.mock_file_data = {
            "userId": self.user_id,
            "projectId": self.project_id,
            "files": [
                {
                    "path": "s3:/bucket/files/mock",
                    "name": "mock_file.c4gh",
                    "bytes": 100,
                    "encrypted_checksums": [{"str": "string"}],
                    "unencrypted_checksums": [{"str": "string"}],
                }
            ],
        }

        self.mock_file_paths = ["s3:/bucket/files/mock", "s3:/bucket/files/mock2", "s3:/bucket/files/mock3"]
        self.mock_single_file = {
            "accessionId": self.projected_file_example["accessionId"],
            "path": self.mock_file_data["files"][0]["path"],
            "projectId": self.mock_file_data["projectId"],
        }

    async def tearDownAsync(self):
        """Cleanup mocked stuff."""
        await super().tearDownAsync()
        self.patch_fileoperator.stop()

    async def test_get_project_files(self) -> None:
        """Test fetching files belonging to specific project."""
        with (
            self.patch_verify_user_project_failure,
            self.patch_verify_authorization,
        ):
            # User is not part of project
            response = await self.client.get(f"{API_PREFIX}/files")
            self.assertEqual(response.status, 401)

        with (
            self.patch_verify_user_project_success,
            self.patch_verify_authorization,
        ):
            # Successful fetching of project-wise file list
            self.MockedFileOperator().read_project_files.return_value = self.test_submission["files"]
            response = await self.client.get(f"{API_PREFIX}/files")
            self.assertEqual(response.status, 200)
            json_resp = await response.json()
            self.assertEqual(json_resp[0]["accessionId"], "file1")

    async def test_post_project_files_works(self) -> None:
        """Test file post request handler."""
        with (
            self.patch_verify_user_project_success,
            self.patch_verify_authorization,
        ):
            self.MockedFileOperator().create_file_or_version.return_value = "accession_id1", 1
            response = await self.client.post(f"{API_PREFIX}/files", json=self.mock_file_data)
            self.assertEqual(response.status, 201)
            json_resp = await response.json()
            self.assertEqual(json_resp, [["accession_id1", 1]])

    async def test_post_project_files_fails(self) -> None:
        """Test file post request handler for error instances."""
        with (
            self.patch_verify_user_project_failure,
            self.patch_verify_authorization,
        ):
            # Requesting user is not part of the project
            response = await self.client.post(f"{API_PREFIX}/files", json=self.mock_file_data)
            self.assertEqual(response.status, 401)

        with (
            self.patch_verify_user_project_success,
            self.patch_verify_authorization,
        ):
            # Faulty request data
            alt_data = self.mock_file_data
            alt_data["files"] = "not a list"
            response = await self.client.post(f"{API_PREFIX}/files", json=alt_data)
            self.assertEqual(response.status, 400)
            json_resp = await response.json()
            self.assertEqual(json_resp["detail"], "Field `files` must be a list.")

            # Lacking request data
            alt_data = self.mock_file_data
            alt_data["files"] = [{"name": "filename"}]
            response = await self.client.post(f"{API_PREFIX}/files", json=alt_data)
            self.assertEqual(response.status, 400)
            json_resp = await response.json()
            self.assertEqual(
                json_resp["detail"],
                "Fields `path`, `name`, `bytes`, `encrypted_checksums`, `unencrypted_checksums` are required.",
            )

    async def test_delete_project_files_works(self) -> None:
        """Test deleting file request handler."""
        with (
            self.patch_verify_user_project_success,
            self.patch_verify_authorization,
        ):
            url = f"{API_PREFIX}/files/{self.mock_single_file['projectId']}"
            self.MockedFileOperator().check_file_exists.return_value = self.mock_single_file
            response = await self.client.delete(url, json=self.mock_file_paths)
            self.assertEqual(self.MockedFileOperator().flag_file_deleted.call_count, 3)
            self.assertEqual(response.status, 204)

    async def test_delete_project_files_not_in_database(self) -> None:
        """Test deleting file request handler with error if file does not exist in database."""
        with (
            self.patch_verify_user_project_success,
            self.patch_verify_authorization,
        ):
            url = f"{API_PREFIX}/files/{self.mock_single_file['projectId']}"
            # File does not exist in database
            self.MockedFileOperator().check_file_exists.return_value = None
            await self.client.delete(url, json=self.mock_file_paths)
            self.MockedFileOperator().flag_file_deleted.assert_not_called()

    async def test_delete_project_files_not_valid(self) -> None:
        """Test deleting file request handler with error if files in request are not valid."""
        with (
            self.patch_verify_user_project_success,
            self.patch_verify_authorization,
        ):
            url = f"{API_PREFIX}/files/{self.mock_single_file['projectId']}"
            # Invalid file as request payload
            await self.client.delete(url, json=self.mock_single_file)
            self.MockedFileOperator().check_file_exists.assert_not_called()
            self.MockedFileOperator().flag_file_deleted.assert_not_called()


class ApiKeyHandlerTestCase(HandlersTestCase):
    """API key handler test cases."""

    async def test_post_get_delete_api_key(self) -> None:
        """Test API key creation, listing and revoking."""

        with (
            self.patch_verify_authorization,
            self.patch_verify_user_project_success,
        ):
            key_id_1 = str(uuid.uuid4())
            key_id_2 = str(uuid.uuid4())

            # Create first key.
            response = await self.client.post(
                f"{API_PREFIX}/api/keys", json=ApiKey(key_id=key_id_1).model_dump(mode="json")
            )
            self.assertEqual(response.status, 200)

            # Check first key exists.
            response = await self.client.get(f"{API_PREFIX}/api/keys")
            self.assertEqual(response.status, 200)
            json = await response.json()
            assert len(json) == 1
            api_key_1 = ApiKey(**json[0])
            self.assertEqual(api_key_1.key_id, key_id_1)
            self.assertIsNotNone(api_key_1.created_at)

            # Create second key.
            response = await self.client.post(
                f"{API_PREFIX}/api/keys", json=ApiKey(key_id=key_id_2).model_dump(mode="json")
            )
            self.assertEqual(response.status, 200)

            # Check first and second key exist.
            response = await self.client.get(f"{API_PREFIX}/api/keys")
            self.assertEqual(response.status, 200)
            json = await response.json()
            assert len(json) == 2

            key_ids = [ApiKey(**key).key_id for key in json]
            assert key_id_1 in key_ids
            assert key_id_2 in key_ids
            self.assertIsNotNone(ApiKey(**json[0]).created_at)
            self.assertIsNotNone(ApiKey(**json[1]).created_at)

            # Remove second key.
            response = await self.client.delete(
                f"{API_PREFIX}/api/keys", json=ApiKey(key_id=key_id_2).model_dump(mode="json")
            )
            self.assertEqual(response.status, 204)

            # Check first key exists.
            response = await self.client.get(f"{API_PREFIX}/api/keys")
            self.assertEqual(response.status, 200)
            json = await response.json()
            assert len(json) == 1
            api_key_1 = ApiKey(**json[0])
            self.assertEqual(api_key_1.key_id, key_id_1)
            self.assertIsNotNone(api_key_1.created_at)


class UserHandlerTestCase(HandlersTestCase):
    """User handler test cases."""

    async def test_get_user(self) -> None:
        """Test getting user information."""

        project_id = "PRJ123"

        with (
            self.patch_verify_authorization,
            patch.dict(
                os.environ,
                {"CSC_LDAP_HOST": "ldap://mockhost", "CSC_LDAP_USER": "mockuser", "CSC_LDAP_PASSWORD": "mockpassword"},
            ),
            patch("metadata_backend.api.services.ldap.Connection") as mock_connection,
        ):
            mock_conn_instance, mock_entry = MagicMock(), MagicMock()
            mock_entry.entry_to_json.return_value = json.dumps(
                {"dn": "ou=SP_SD-SUBMIT,ou=idm,dc=csc,dc=fi", "attributes": {"CSCPrjNum": [project_id]}}
            )
            mock_conn_instance.entries = [mock_entry]
            mock_connection.return_value.__enter__.return_value = mock_conn_instance

            response = await self.client.get(f"{API_PREFIX}/users")
            self.assertEqual(response.status, 200)

            user = User(**await response.json())
            assert user.user_id == "mock-userid"
            assert user.user_name == "mock-username"
            assert user.projects == [Project(project_id=project_id)]
