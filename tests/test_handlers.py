"""Test API endpoints from handlers module."""

from pathlib import Path
from unittest.mock import AsyncMock, call, patch
import time

import ujson
from aiohttp import FormData
from aiohttp.test_utils import AioHTTPTestCase, make_mocked_coro
from metadata_backend.api.handlers.object import ObjectAPIHandler
from metadata_backend.api.handlers.restapi import RESTAPIHandler
import aiohttp_session

from metadata_backend.conf.conf import API_PREFIX
from metadata_backend.server import init


class HandlersTestCase(AioHTTPTestCase):
    """API endpoint class test cases."""

    TESTFILES_ROOT = Path(__file__).parent / "test_files"

    async def get_application(self):
        """Retrieve web Application for test."""
        server = await init()
        return server

    async def setUpAsync(self):
        """Configure default values for testing and other modules.

        This patches used modules and sets default return values for their
        methods. Also sets up reusable test variables for different test
        methods.
        """
        self.app = await self.get_application()
        self.server = await self.get_server(self.app)
        self.client = await self.get_client(self.server)

        self.session_return = aiohttp_session.Session(
            "test-identity",
            new=True,
            data={},
        )

        self.session_return["access_token"] = "not-really-a-token"  # nosec
        self.session_return["at"] = time.time()
        self.session_return["user_info"] = "value"
        self.session_return["oidc_state"] = "state"

        self.aiohttp_session_get_session_mock = AsyncMock()
        self.aiohttp_session_get_session_mock.return_value = self.session_return
        self.p_get_sess_restapi = patch(
            "metadata_backend.api.handlers.restapi.aiohttp_session.get_session",
            self.aiohttp_session_get_session_mock,
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
        self.test_submission = {
            "projectId": self.project_id,
            "submissionId": self.submission_id,
            "name": "mock submission",
            "description": "test mock submission",
            "published": False,
            "metadataObjects": [
                {"accessionId": "EDAG3991701442770179", "schema": "study"},
                {"accessionId": "EGA123456", "schema": "sample"},
            ],
            "drafts": [],
            "doiInfo": {"creators": [{"name": "Creator, Test"}]},
        }
        self.user_id = "USR12345678"
        self.test_user = {
            "userId": self.user_id,
            "name": "tester",
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
            "query_metadata_database.side_effect": self.fake_operator_query_metadata_object,
            "create_metadata_object.side_effect": self.fake_operator_create_metadata_object,
            "delete_metadata_object.side_effect": self.fake_operator_delete_metadata_object,
            "update_metadata_object.side_effect": self.fake_operator_update_metadata_object,
            "replace_metadata_object.side_effect": self.fake_operator_replace_metadata_object,
            "create_metax_info.side_effect": self.fake_operator_create_metax_info,
        }
        self.xmloperator_config = {
            "read_metadata_object.side_effect": self.fake_xmloperator_read_metadata_object,
            "create_metadata_object.side_effect": self.fake_xmloperator_create_metadata_object,
            "replace_metadata_object.side_effect": self.fake_xmloperator_replace_metadata_object,
        }
        self.submissionoperator_config = {
            "create_submission.side_effect": self.fake_submissionoperator_create_submission,
            "read_submission.side_effect": self.fake_submissionoperator_read_submission,
            "delete_submission.side_effect": self.fake_submissionoperator_delete_submission,
            "check_object_in_submission.side_effect": self.fake_submissionoperator_check_object,
        }
        self.useroperator_config = {
            "create_user.side_effect": self.fake_useroperator_create_user,
            "read_user.side_effect": self.fake_useroperator_read_user,
            "filter_user.side_effect": self.fake_useroperator_filter_user,
        }

        self.doi_handler = {
            "create_draft.side_effect": self.fake_doi_create_draft,
            "set_state.side_effect": self.fake_doi_set_state,
            "delete.side_effect": self.fake_doi_delete,
        }

        RESTAPIHandler._handle_check_ownership = make_mocked_coro(True)
        ObjectAPIHandler._delete_metax_dataset = make_mocked_coro()

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

    async def fake_doi_create_draft(self, prefix):
        """."""
        return {"fullDOI": "10.xxxx/yyyyy", "dataset": "https://doi.org/10.xxxx/yyyyy"}

    async def fake_doi_set_state(self, data):
        """."""
        return {"fullDOI": "10.xxxx/yyyyy", "dataset": "https://doi.org/10.xxxx/yyyyy"}

    async def fake_doi_delete(self, doi):
        """."""
        return None

    async def fake_operator_read_metadata_object(self, schema_type, accession_id):
        """Fake read operation to return mocked JSON."""
        return (self.metadata_json, "application/json")

    async def fake_operator_query_metadata_object(self, schema_type, query, page_num, page_size, filtered_list):
        """Fake query operation to return list containing mocked JSON."""
        return ([self.metadata_json], self.page_num, self.page_size, self.total_objects)

    async def fake_xmloperator_read_metadata_object(self, schema_type, accession_id):
        """Fake read operation to return mocked xml."""
        return (self.metadata_xml, "text/xml")

    async def fake_xmloperator_create_metadata_object(self, schema_type, content):
        """Fake create operation to return mocked accessionId."""
        return {"accessionId": self.test_ega_string}

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

    async def fake_operator_create_metax_info(self, schema_type, accession_id, data):
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
        data = True, self.submission_id, False
        return data

    async def fake_useroperator_create_user(self, content):
        """Fake user operation to return mocked userId."""
        return self.user_id

    async def fake_useroperator_read_user(self, user_id):
        """Fake read operation to return mocked user."""
        return self.test_user

    async def fake_useroperator_filter_user(self, query, item_type, page, per_page):
        """Fake read operation to return mocked user."""
        return self.test_user[item_type], len(self.test_user[item_type])


class APIHandlerTestCase(HandlersTestCase):
    """Schema API endpoint class test cases."""

    async def test_correct_schema_types_are_returned(self):
        """Test API endpoint for all schema types."""
        with self.p_get_sess_restapi:
            response = await self.client.get(f"{API_PREFIX}/schemas")
            response_text = await response.text()
            schema_types = [
                "submission",
                "study",
                "sample",
                "experiment",
                "run",
                "analysis",
                "dac",
                "policy",
                "dataset",
                "project",
            ]

            for schema_type in schema_types:
                self.assertIn(schema_type, response_text)

    async def test_correct_study_schema_are_returned(self):
        """Test API endpoint for study schema types."""
        with self.p_get_sess_restapi:
            response = await self.client.get(f"{API_PREFIX}/schemas/study")
            response_text = await response.text()
            self.assertIn("study", response_text)
            self.assertNotIn("submission", response_text)

    async def test_raises_invalid_schema(self):
        """Test API endpoint for study schema types."""
        with self.p_get_sess_restapi:
            response = await self.client.get(f"{API_PREFIX}/schemas/something")
            self.assertEqual(response.status, 404)

    async def test_raises_not_found_schema(self):
        """Test API endpoint for study schema types."""
        with self.p_get_sess_restapi:
            response = await self.client.get(f"{API_PREFIX}/schemas/project")
            self.assertEqual(response.status, 400)
            resp_json = await response.json()
            self.assertEqual(resp_json["detail"], "The provided schema type could not be found. (project)")


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

        class_xmloperator = "metadata_backend.api.handlers.xml_submission.XMLOperator"
        self.patch_xmloperator = patch(class_xmloperator, **self.xmloperator_config, spec=True)
        self.MockedXMLOperator = self.patch_xmloperator.start()

    async def tearDownAsync(self):
        """Cleanup mocked stuff."""
        await super().tearDownAsync()
        self.patch_parser.stop()
        self.patch_xmloperator.stop()

    async def test_submit_endpoint_submission_does_not_fail(self):
        """Test that submission with valid SUBMISSION.xml does not fail."""
        with self.p_get_sess_restapi:
            files = [("submission", "ERA521986_valid.xml")]
            data = self.create_submission_data(files)
            response = await self.client.post(f"{API_PREFIX}/submit", data=data)
            self.assertEqual(response.status, 200)
            self.assertEqual(response.content_type, "application/json")

    async def test_submit_endpoint_fails_without_submission_xml(self):
        """Test that basic POST submission fails with no submission.xml.

        User should also be notified for missing file.
        """
        with self.p_get_sess_restapi:
            files = [("analysis", "ERZ266973.xml")]
            data = self.create_submission_data(files)
            response = await self.client.post(f"{API_PREFIX}/submit", data=data)
            failure_text = "There must be a submission.xml file in submission."
            self.assertEqual(response.status, 400)
            self.assertIn(failure_text, await response.text())

    async def test_submit_endpoint_fails_with_many_submission_xmls(self):
        """Test submission fails when there's too many submission.xml -files.

        User should be notified for submitting too many files.
        """
        with self.p_get_sess_restapi:
            files = [("submission", "ERA521986_valid.xml"), ("submission", "ERA521986_valid2.xml")]
            data = self.create_submission_data(files)
            response = await self.client.post(f"{API_PREFIX}/submit", data=data)
            failure_text = "You should submit only one submission.xml file."
            self.assertEqual(response.status, 400)
            self.assertIn(failure_text, await response.text())

    async def test_validation_passes_for_valid_xml(self):
        """Test validation endpoint for valid xml."""
        with self.p_get_sess_restapi:
            files = [("study", "SRP000539.xml")]
            data = self.create_submission_data(files)
            response = await self.client.post(f"{API_PREFIX}/validate", data=data)
            self.assertEqual(response.status, 200)
            self.assertIn('{"isValid":true}', await response.text())

    async def test_validation_fails_bad_schema(self):
        """Test validation fails for bad schema and valid xml."""
        with self.p_get_sess_restapi:
            files = [("fake", "SRP000539.xml")]
            data = self.create_submission_data(files)
            response = await self.client.post(f"{API_PREFIX}/validate", data=data)
            self.assertEqual(response.status, 404)

    async def test_validation_fails_for_invalid_xml_syntax(self):
        """Test validation endpoint for XML with bad syntax."""
        with self.p_get_sess_restapi:
            files = [("study", "SRP000539_invalid.xml")]
            data = self.create_submission_data(files)
            response = await self.client.post(f"{API_PREFIX}/validate", data=data)
            resp_dict = await response.json()
            self.assertEqual(response.status, 200)
            self.assertIn("Faulty XML file was given, mismatched tag", resp_dict["detail"]["reason"])

    async def test_validation_fails_for_invalid_xml(self):
        """Test validation endpoint for invalid xml."""
        with self.p_get_sess_restapi:
            files = [("study", "SRP000539_invalid2.xml")]
            data = self.create_submission_data(files)
            response = await self.client.post(f"{API_PREFIX}/validate", data=data)
            resp_dict = await response.json()
            self.assertEqual(response.status, 200)
            self.assertIn("value must be one of", resp_dict["detail"]["reason"])

    async def test_validation_fails_with_too_many_files(self):
        """Test validation endpoint for too many files."""
        with self.p_get_sess_restapi:
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

        self._mock_draft_doi = "metadata_backend.api.handlers.object.ObjectAPIHandler._draft_doi"

        class_doihandler = "metadata_backend.api.handlers.object.DOIHandler"
        self.patch_doihandler = patch(class_doihandler, **self.doi_handler, spec=True)
        self.MockedDoiHandler = self.patch_doihandler.start()

        class_xmloperator = "metadata_backend.api.handlers.object.XMLOperator"
        self.patch_xmloperator = patch(class_xmloperator, **self.xmloperator_config, spec=True)
        self.MockedXMLOperator = self.patch_xmloperator.start()

        class_operator = "metadata_backend.api.handlers.object.Operator"
        self.patch_operator = patch(class_operator, **self.operator_config, spec=True)
        self.MockedOperator = self.patch_operator.start()

        class_csv_parser = "metadata_backend.api.handlers.common.CSVToJSONParser"
        self.patch_csv_parser = patch(class_csv_parser, spec=True)
        self.MockedCSVParser = self.patch_csv_parser.start()

        class_submissionoperator = "metadata_backend.api.handlers.object.SubmissionOperator"
        self.patch_submissionoperator = patch(class_submissionoperator, **self.submissionoperator_config, spec=True)
        self.MockedSubmissionOperator = self.patch_submissionoperator.start()

        class_metaxhandler = "metadata_backend.api.handlers.object.MetaxServiceHandler"
        self.patch_metaxhandler = patch(class_metaxhandler, spec=True)
        self.MockedMetaxHandler = self.patch_metaxhandler.start()
        self.MockedMetaxHandler().post_dataset_as_draft.return_value = "123-456"

    async def tearDownAsync(self):
        """Cleanup mocked stuff."""
        await super().tearDownAsync()
        self.patch_xmloperator.stop()
        self.patch_csv_parser.stop()
        self.patch_submissionoperator.stop()
        self.patch_operator.stop()
        self.patch_metaxhandler.stop()
        self.patch_doihandler.stop()

    async def test_submit_object_works(self):
        """Test that submission is handled, XMLOperator is called."""
        files = [("study", "SRP000539.xml")]
        data = self.create_submission_data(files)
        with patch(self._mock_draft_doi, return_value=self._draft_doi_data), self.p_get_sess_restapi:
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
        with patch(self._mock_draft_doi, return_value=self._draft_doi_data), self.p_get_sess_restapi:
            response = await self.client.post(
                f"{API_PREFIX}/objects/study", params={"submission": "some id"}, json=json_req
            )
            self.assertEqual(response.status, 201)
            self.assertIn(self.test_ega_string, await response.text())
            self.MockedOperator().create_metadata_object.assert_called_once()

    async def test_submit_object_missing_field_json(self):
        """Test that JSON has missing property."""
        with self.p_get_sess_restapi:
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
        with self.p_get_sess_restapi:
            response = await self.client.post(
                f"{API_PREFIX}/objects/study", params={"submission": "some id"}, json=json_req
            )
            reason = "Provided input does not seem correct for field: 'descriptor'"
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
        with self.p_get_sess_restapi:
            response = await self.client.post(
                f"{API_PREFIX}/objects/study", params={"submission": "some id"}, data=json_req
            )
            reason = "JSON is not correctly formatted. See: Expecting value: line 1 column 1"
            self.assertEqual(response.status, 400)
            self.assertIn(reason, await response.text())

    async def test_post_object_works_with_csv(self):
        """Test that CSV file is parsed and submitted as json."""
        files = [("sample", "EGAformat.csv")]
        data = self.create_submission_data(files)
        file_content = self.get_file_data("sample", "EGAformat.csv")
        self.MockedCSVParser().parse.return_value = [{}, {}, {}]
        with self.p_get_sess_restapi:
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
        with self.p_get_sess_restapi:
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
        with self.p_get_sess_restapi:
            response = await self.client.put(call, data=json_req)
            reason = "JSON is not correctly formatted. See: Expecting value: line 1 column 1"
            self.assertEqual(response.status, 400)
            self.assertIn(reason, await response.text())

    async def test_patch_object_bad_json(self):
        """Test that patch JSON is badly formated."""
        json_req = {"centerName": "GEO", "alias": "GSE10966"}
        call = f"{API_PREFIX}/drafts/study/EGA123456"
        with self.p_get_sess_restapi:
            response = await self.client.patch(call, data=json_req)
            reason = "JSON is not correctly formatted. See: Expecting value: line 1 column 1"
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
        with self.p_get_sess_restapi:
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
        with self.p_get_sess_restapi:
            response = await self.client.put(call, json=json_req)
            self.assertEqual(response.status, 200)
            self.assertIn(self.test_ega_string, await response.text())
            self.MockedOperator().replace_metadata_object.assert_called_once()

    async def test_put_draft_works_with_xml(self):
        """Test that put XML submisssion is handled, XMLOperator is called."""
        files = [("study", "SRP000539.xml")]
        data = self.create_submission_data(files)
        call = f"{API_PREFIX}/drafts/study/EGA123456"
        with self.p_get_sess_restapi:
            response = await self.client.put(call, data=data)
            self.assertEqual(response.status, 200)
            self.assertIn(self.test_ega_string, await response.text())
            self.MockedXMLOperator().replace_metadata_object.assert_called_once()

    async def test_patch_draft_works_with_json(self):
        """Test that draft JSON patch method is handled, operator is called."""
        json_req = {"centerName": "GEO", "alias": "GSE10966"}
        call = f"{API_PREFIX}/drafts/study/EGA123456"
        with self.p_get_sess_restapi:
            response = await self.client.patch(call, json=json_req)
            self.assertEqual(response.status, 200)
            self.assertIn(self.test_ega_string, await response.text())
            self.MockedOperator().update_metadata_object.assert_called_once()

    async def test_patch_draft_raises_with_xml(self):
        """Test that patch XML submisssion raises error."""
        with self.p_get_sess_restapi:
            files = [("study", "SRP000539.xml")]
            data = self.create_submission_data(files)
            call = f"{API_PREFIX}/drafts/study/EGA123456"
            response = await self.client.patch(call, data=data)
            self.assertEqual(response.status, 415)

    async def test_submit_object_fails_with_too_many_files(self):
        """Test that sending two files to endpoint results failure."""
        with self.p_get_sess_restapi:
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
        with self.p_get_sess_restapi:
            url = f"{API_PREFIX}/objects/study/{self.query_accessionId}"
            response = await self.client.get(url)
            self.assertEqual(response.status, 200)
            self.assertEqual(response.content_type, "application/json")
            self.assertEqual(self.metadata_json, await response.json())

    async def test_get_draft_object(self):
        """Test that draft accessionId returns correct JSON object."""
        with self.p_get_sess_restapi:
            url = f"{API_PREFIX}/drafts/study/{self.query_accessionId}"
            response = await self.client.get(url)
            self.assertEqual(response.status, 200)
            self.assertEqual(response.content_type, "application/json")
            self.assertEqual(self.metadata_json, await response.json())

    async def test_get_object_as_xml(self):
        """Test that accessionId  with XML query returns XML object."""
        url = f"{API_PREFIX}/objects/study/{self.query_accessionId}"
        with self.p_get_sess_restapi:
            response = await self.client.get(f"{url}?format=xml")
            self.assertEqual(response.status, 200)
            self.assertEqual(response.content_type, "text/xml")
            self.assertEqual(self.metadata_xml, await response.text())

    async def test_query_is_called_and_returns_json_in_correct_format(self):
        """Test query method calls operator and returns mocked JSON object."""
        url = f"{API_PREFIX}/objects/study?studyType=foo&name=bar&page={self.page_num}" f"&per_page={self.page_size}"
        with self.p_get_sess_restapi:
            response = await self.client.get(url)
            self.assertEqual(response.status, 200)
            self.assertEqual(response.content_type, "application/json")
            json_resp = await response.json()
            self.assertEqual(json_resp["page"]["page"], self.page_num)
            self.assertEqual(json_resp["page"]["size"], self.page_size)
            self.assertEqual(json_resp["page"]["totalPages"], (self.total_objects / self.page_size))
            self.assertEqual(json_resp["page"]["totalObjects"], self.total_objects)
            self.assertEqual(json_resp["objects"][0], self.metadata_json)
            self.MockedOperator().query_metadata_database.assert_called_once()
            args = self.MockedOperator().query_metadata_database.call_args[0]
            self.assertEqual("study", args[0])
            self.assertIn("studyType': 'foo', 'name': 'bar'", str(args[1]))
            self.assertEqual(self.page_num, args[2])
            self.assertEqual(self.page_size, args[3])

    async def test_delete_is_called(self):
        """Test query method calls operator and returns status correctly."""
        url = f"{API_PREFIX}/objects/study/EGA123456"
        with patch(
            "metadata_backend.api.handlers.object.DOIHandler.delete", return_value=None
        ), self.p_get_sess_restapi:
            response = await self.client.delete(url)
            self.assertEqual(response.status, 204)
            self.MockedOperator().delete_metadata_object.assert_called_once()

    async def test_query_fails_with_xml_format(self):
        """Test query method calls operator and returns status correctly."""
        url = f"{API_PREFIX}/objects/study?studyType=foo&name=bar&format=xml"
        with self.p_get_sess_restapi:
            response = await self.client.get(url)
            json_resp = await response.json()
            self.assertEqual(response.status, 400)
            self.assertIn("xml-formatted query results are not supported", json_resp["detail"])

    async def test_operations_fail_for_wrong_schema_type(self):
        """Test 404 error is raised if incorrect schema name is given."""
        with self.p_get_sess_restapi:
            get_resp = await self.client.get(f"{API_PREFIX}/objects/bad_scehma_name/some_id")
            self.assertEqual(get_resp.status, 404)
            json_get_resp = await get_resp.json()
            self.assertIn("Specified schema", json_get_resp["detail"])

            post_rep = await self.client.post(f"{API_PREFIX}/objects/bad_scehma_name", params={"submission": "some id"})
            self.assertEqual(post_rep.status, 404)
            post_json_rep = await post_rep.json()
            self.assertIn("Specified schema", post_json_rep["detail"])

            get_resp = await self.client.get(f"{API_PREFIX}/objects/bad_scehma_name")
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

    async def test_query_with_invalid_pagination_params(self):
        """Test that 400s are raised correctly with pagination."""
        with self.p_get_sess_restapi:
            get_resp = await self.client.get(f"{API_PREFIX}/objects/study?page=2?title=joo")
            self.assertEqual(get_resp.status, 400)
            get_resp = await self.client.get(f"{API_PREFIX}/objects/study?page=0")
            self.assertEqual(get_resp.status, 400)
            get_resp = await self.client.get(f"{API_PREFIX}/objects/study?per_page=0")
            self.assertEqual(get_resp.status, 400)


class UserHandlerTestCase(HandlersTestCase):
    """User API endpoint class test cases."""

    async def setUpAsync(self):
        """Configure default values for testing and other modules.

        This patches used modules and sets default return values for their
        methods.
        """

        await super().setUpAsync()
        class_useroperator = "metadata_backend.api.handlers.user.UserOperator"
        self.patch_useroperator = patch(class_useroperator, **self.useroperator_config, spec=True)
        self.MockedUserOperator = self.patch_useroperator.start()

    async def tearDownAsync(self):
        """Cleanup mocked stuff."""
        await super().tearDownAsync()
        self.patch_useroperator.stop()

    async def test_get_user_works(self):
        """Test user object is returned when correct user id is given."""
        with self.p_get_sess_restapi:
            response = await self.client.get(f"{API_PREFIX}/users/current")
            self.assertEqual(response.status, 200)
            self.MockedUserOperator().read_user.assert_called_once()
            json_resp = await response.json()
            self.assertEqual(self.test_user, json_resp)

    async def test_user_deletion_is_called(self):
        """Test that user object would be deleted."""
        with self.p_get_sess_restapi:
            self.MockedUserOperator().read_user.return_value = self.test_user
            self.MockedUserOperator().delete_user.return_value = None
            await self.client.delete(f"{API_PREFIX}/users/current")
            self.MockedUserOperator().delete_user.assert_called_once()


class SubmissionHandlerTestCase(HandlersTestCase):
    """Submission API endpoint class test cases."""

    async def setUpAsync(self):
        """Configure default values for testing and other modules.

        This patches used modules and sets default return values for their
        methods.
        """

        await super().setUpAsync()

        class_doihandler = "metadata_backend.api.handlers.submission.DOIHandler"
        self.patch_doihandler = patch(class_doihandler, **self.doi_handler, spec=True)
        self.MockedDoiHandler = self.patch_doihandler.start()

        self._mock_prepare_doi = "metadata_backend.api.handlers.submission.SubmissionAPIHandler._prepare_doi_update"

        class_submissionoperator = "metadata_backend.api.handlers.submission.SubmissionOperator"
        self.patch_submissionoperator = patch(class_submissionoperator, **self.submissionoperator_config, spec=True)
        self.MockedSubmissionOperator = self.patch_submissionoperator.start()

        class_useroperator = "metadata_backend.api.handlers.submission.UserOperator"
        self.patch_useroperator = patch(class_useroperator, **self.useroperator_config, spec=True)
        self.MockedUserOperator = self.patch_useroperator.start()

        class_operator = "metadata_backend.api.handlers.submission.Operator"
        self.patch_operator = patch(class_operator, **self.operator_config, spec=True)
        self.MockedOperator = self.patch_operator.start()

        class_metaxhandler = "metadata_backend.api.handlers.submission.MetaxServiceHandler"
        self.patch_metaxhandler = patch(class_metaxhandler, spec=True)
        self.MockedMetaxHandler = self.patch_metaxhandler.start()

    async def tearDownAsync(self):
        """Cleanup mocked stuff."""
        await super().tearDownAsync()
        self.patch_doihandler.stop()
        self.patch_submissionoperator.stop()
        self.patch_useroperator.stop()
        self.patch_operator.stop()
        self.patch_metaxhandler.stop()

    async def test_submission_creation_works(self):
        """Test that submission is created and submission ID returned."""
        json_req = {"name": "test", "description": "test submission", "projectId": "1000"}
        with patch(
            "metadata_backend.api.operators.ProjectOperator._check_project_exists",
            return_value=True,
        ), self.p_get_sess_restapi:
            response = await self.client.post(f"{API_PREFIX}/submissions", json=json_req)
            json_resp = await response.json()
            self.MockedSubmissionOperator().create_submission.assert_called_once()
            self.assertEqual(response.status, 201)
            self.assertEqual(json_resp["submissionId"], self.submission_id)

    async def test_submission_creation_with_missing_name_fails(self):
        """Test that submission creation fails when missing name in request."""
        json_req = {"description": "test submission", "projectId": "1000"}
        with self.p_get_sess_restapi:
            response = await self.client.post(f"{API_PREFIX}/submissions", json=json_req)
            json_resp = await response.json()
            self.assertEqual(response.status, 400)
            self.assertIn("'name' is a required property", json_resp["detail"])

    async def test_submission_creation_with_missing_project_fails(self):
        """Test that submission creation fails when missing project in request."""
        json_req = {"description": "test submission", "name": "name"}
        with self.p_get_sess_restapi:
            response = await self.client.post(f"{API_PREFIX}/submissions", json=json_req)
            json_resp = await response.json()
            self.assertEqual(response.status, 400)
            self.assertIn("'projectId' is a required property", json_resp["detail"])

    async def test_submission_creation_with_empty_body_fails(self):
        """Test that submission creation fails when no data in request."""
        with self.p_get_sess_restapi:
            response = await self.client.post(f"{API_PREFIX}/submissions")
            json_resp = await response.json()
            self.assertEqual(response.status, 400)
            self.assertIn("JSON is not correctly formatted.", json_resp["detail"])

    async def test_get_submissions_with_1_submission(self):
        """Test get_submissions() endpoint returns list with 1 submission."""
        self.MockedSubmissionOperator().query_submissions.return_value = (self.test_submission, 1)
        with self.p_get_sess_restapi:
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
        with self.p_get_sess_restapi:
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
        with self.p_get_sess_restapi:
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
        with self.p_get_sess_restapi:
            response = await self.client.get(f"{API_PREFIX}/submissions/FOL12345678")
            self.assertEqual(response.status, 200)
            self.MockedSubmissionOperator().read_submission.assert_called_once()
            json_resp = await response.json()
            self.assertEqual(self.test_submission, json_resp)

    async def test_update_submission_fails_with_wrong_key(self):
        """Test that submission does not update when wrong keys are provided."""
        data = [{"op": "add", "path": f"{API_PREFIX}/objects"}]
        with self.p_get_sess_restapi:
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
        with self.p_get_sess_restapi:
            response = await self.client.patch(f"{API_PREFIX}/submissions/FOL12345678", json=data)
            self.MockedSubmissionOperator().update_submission.assert_called_once()
            self.assertEqual(response.status, 200)
            json_resp = await response.json()
            self.assertEqual(json_resp["submissionId"], self.submission_id)

    async def test_submission_is_published(self):
        """Test that submission would be published and DOI would be added."""
        self.MockedDoiHandler().set_state.return_value = None
        self.MockedSubmissionOperator().update_submission.return_value = self.submission_id
        self.MockedMetaxHandler().update_dataset_with_doi_info.return_value = None
        self.MockedMetaxHandler().publish_dataset.return_value = None
        with patch(
            self._mock_prepare_doi,
            return_value=(
                {"id": "prefix/suffix-study", "attributes": {"url": "http://metax_id", "types": {}}},
                [{"id": "prefix/suffix-dataset", "attributes": {"url": "http://metax_id", "types": {}}}],
                [
                    {"doi": "prefix/suffix-study", "metaxIdentifier": "metax_id"},
                    {"doi": "prefix/suffix-dataset", "metaxIdentifier": "metax_id"},
                ],
            ),
        ), self.p_get_sess_restapi:
            response = await self.client.patch(f"{API_PREFIX}/publish/FOL12345678")
            self.assertEqual(response.status, 200)
            json_resp = await response.json()
            self.assertEqual(json_resp["submissionId"], self.submission_id)

    async def test_submission_deletion_is_called(self):
        """Test that submission would be deleted."""
        self.MockedSubmissionOperator().read_submission.return_value = self.test_submission
        with self.p_get_sess_restapi:
            response = await self.client.delete(f"{API_PREFIX}/submissions/FOL12345678")
            self.MockedSubmissionOperator().read_submission.assert_called_once()
            self.MockedSubmissionOperator().delete_submission.assert_called_once()
            self.assertEqual(response.status, 204)

    async def test_put_submission_doi_passes_and_returns_id(self):
        """Test put method for submission doi works."""
        self.MockedSubmissionOperator().update_submission.return_value = self.submission_id
        data = ujson.load(open(self.TESTFILES_ROOT / "doi" / "test_doi.json"))

        with self.p_get_sess_restapi:
            response = await self.client.put(f"{API_PREFIX}/submissions/FOL12345678/doi", json=data)
            self.assertEqual(response.status, 200)
            json_resp = await response.json()
            self.assertEqual(json_resp["submissionId"], self.submission_id)

            response = await self.client.get(f"{API_PREFIX}/submissions/{self.submission_id}")
            self.assertEqual(response.status, 200)
            json_resp = await response.json()
            self.assertIn("doiInfo", json_resp)
