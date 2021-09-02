"""Test API endpoints from handlers module."""

from pathlib import Path
from unittest.mock import patch

from aiohttp import FormData
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from metadata_backend.api.middlewares import generate_cookie
from .mockups import get_request_with_fernet
from metadata_backend.server import init


class HandlersTestCase(AioHTTPTestCase):
    """API endpoint class test cases."""

    TESTFILES_ROOT = Path(__file__).parent / "test_files"

    async def get_application(self):
        """Retrieve web Application for test."""
        server = await init()
        server["Session"] = {"user_info": ["value", "value"]}
        return server

    async def setUpAsync(self):
        """Configure default values for testing and other modules.

        This patches used modules and sets default return values for their
        methods. Also sets up reusable test variables for different test
        methods.
        """
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
        self.folder_id = "FOL12345678"
        self.test_folder = {
            "folderId": self.folder_id,
            "name": "mock folder",
            "description": "test mock folder",
            "published": False,
            "metadataObjects": [
                {"accessionId": "EDAG3991701442770179", "schema": "study"},
                {"accessionId": "EGA123456", "schema": "sample"},
            ],
            "drafts": [],
        }
        self.user_id = "USR12345678"
        self.test_user = {
            "userId": self.user_id,
            "name": "tester",
            "drafts": [],
            "folders": ["FOL12345678"],
        }

        class_parser = "metadata_backend.api.handlers.XMLToJSONParser"
        class_operator = "metadata_backend.api.handlers.Operator"
        class_xmloperator = "metadata_backend.api.handlers.XMLOperator"
        class_folderoperator = "metadata_backend.api.handlers.FolderOperator"
        class_useroperator = "metadata_backend.api.handlers.UserOperator"
        operator_config = {
            "read_metadata_object.side_effect": self.fake_operator_read_metadata_object,
            "query_metadata_database.side_effect": self.fake_operator_query_metadata_object,
            "create_metadata_object.side_effect": self.fake_operator_create_metadata_object,
            "delete_metadata_object.side_effect": self.fake_operator_delete_metadata_object,
            "update_metadata_object.side_effect": self.fake_operator_update_metadata_object,
            "replace_metadata_object.side_effect": self.fake_operator_replace_metadata_object,
        }
        xmloperator_config = {
            "read_metadata_object.side_effect": self.fake_xmloperator_read_metadata_object,
            "create_metadata_object.side_effect": self.fake_xmloperator_create_metadata_object,
            "replace_metadata_object.side_effect": self.fake_xmloperator_replace_metadata_object,
        }
        folderoperator_config = {
            "create_folder.side_effect": self.fake_folderoperator_create_folder,
            "read_folder.side_effect": self.fake_folderoperator_read_folder,
            "delete_folder.side_effect": self.fake_folderoperator_delete_folder,
            "check_object_in_folder.side_effect": self.fake_folderoperator_check_object,
            "get_collection_objects.side_effect": self.fake_folderoperator_get_collection_objects,
        }
        useroperator_config = {
            "create_user.side_effect": self.fake_useroperator_create_user,
            "read_user.side_effect": self.fake_useroperator_read_user,
            "filter_user.side_effect": self.fake_useroperator_filter_user,
            "check_user_has_doc.side_effect": self.fake_useroperator_user_has_folder,
        }
        self.patch_parser = patch(class_parser, spec=True)
        self.patch_operator = patch(class_operator, **operator_config, spec=True)
        self.patch_xmloperator = patch(class_xmloperator, **xmloperator_config, spec=True)
        self.patch_folderoperator = patch(class_folderoperator, **folderoperator_config, spec=True)
        self.patch_useroperator = patch(class_useroperator, **useroperator_config, spec=True)
        self.MockedParser = self.patch_parser.start()
        self.MockedOperator = self.patch_operator.start()
        self.MockedXMLOperator = self.patch_xmloperator.start()
        self.MockedFolderOperator = self.patch_folderoperator.start()
        self.MockedUserOperator = self.patch_useroperator.start()

        # Set up authentication
        request = get_request_with_fernet()
        request.app["Crypt"] = self.client.app["Crypt"]
        cookie, cookiestring = generate_cookie(request)
        self.client.app["Session"] = {cookie["id"]: {"access_token": "mock_token_value", "user_info": {}}}
        self.client._session.cookie_jar.update_cookies({"MTD_SESSION": cookiestring})

    async def tearDownAsync(self):
        """Cleanup mocked stuff."""
        self.patch_parser.stop()
        self.patch_operator.stop()
        self.patch_xmloperator.stop()
        self.patch_folderoperator.stop()
        self.patch_useroperator.stop()

    def create_submission_data(self, files):
        """Create request data from pairs of schemas and filenames."""
        data = FormData()
        for schema, filename in files:
            schema_path = "study" if schema == "fake" else schema
            path_to_file = self.TESTFILES_ROOT / schema_path / filename
            data.add_field(
                schema.upper(), open(path_to_file.as_posix(), "r"), filename=path_to_file.name, content_type="text/xml"
            )
        return data

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
        return self.test_ega_string

    async def fake_xmloperator_replace_metadata_object(self, schema_type, accession_id, content):
        """Fake replace operation to return mocked accessionId."""
        return self.test_ega_string

    async def fake_operator_create_metadata_object(self, schema_type, content):
        """Fake create operation to return mocked accessionId."""
        return self.test_ega_string

    async def fake_operator_update_metadata_object(self, schema_type, accession_id, content):
        """Fake update operation to return mocked accessionId."""
        return self.test_ega_string

    async def fake_operator_replace_metadata_object(self, schema_type, accession_id, content):
        """Fake replace operation to return mocked accessionId."""
        return self.test_ega_string

    async def fake_operator_delete_metadata_object(self, schema_type, accession_id):
        """Fake delete operation to await successful operation indicator."""
        return True

    async def fake_folderoperator_create_folder(self, content):
        """Fake create operation to return mocked folderId."""
        return self.folder_id

    async def fake_folderoperator_read_folder(self, folder_id):
        """Fake read operation to return mocked folder."""
        return self.test_folder

    async def fake_folderoperator_delete_folder(self, folder_id):
        """Fake delete folder to await nothing."""
        return None

    async def fake_folderoperator_check_object(self, schema_type, accession_id):
        """Fake check object in folder."""
        data = True, self.folder_id, False
        return data

    async def fake_folderoperator_get_collection_objects(self, schema_type, accession_id):
        """Fake get collection of objects in folder."""
        return ["EDAG3991701442770179", "EGA123456"]

    async def fake_useroperator_user_has_folder(self, schema_type, user_id, folder_id):
        """Fake check object in folder."""
        return True

    async def fake_useroperator_create_user(self, content):
        """Fake user operation to return mocked userId."""
        return self.user_id

    async def fake_useroperator_read_user(self, user_id):
        """Fake read operation to return mocked user."""
        return self.test_user

    async def fake_useroperator_filter_user(self, query, item_type, page, per_page):
        """Fake read operation to return mocked user."""
        return self.test_user[item_type], len(self.test_user[item_type])

    @unittest_run_loop
    async def test_submit_endpoint_submission_does_not_fail(self):
        """Test that submission with valid SUBMISSION.xml does not fail."""
        files = [("submission", "ERA521986_valid.xml")]
        data = self.create_submission_data(files)
        response = await self.client.post("/submit", data=data)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, "application/json")

    @unittest_run_loop
    async def test_submit_endpoint_fails_without_submission_xml(self):
        """Test that basic POST submission fails with no submission.xml.

        User should also be notified for missing file.
        """
        files = [("analysis", "ERZ266973.xml")]
        data = self.create_submission_data(files)
        response = await self.client.post("/submit", data=data)
        failure_text = "There must be a submission.xml file in submission."
        self.assertEqual(response.status, 400)
        self.assertIn(failure_text, await response.text())

    @unittest_run_loop
    async def test_submit_endpoint_fails_with_many_submission_xmls(self):
        """Test submission fails when there's too many submission.xml -files.

        User should be notified for submitting too many files.
        """
        files = [("submission", "ERA521986_valid.xml"), ("submission", "ERA521986_valid2.xml")]
        data = self.create_submission_data(files)
        response = await self.client.post("/submit", data=data)
        failure_text = "You should submit only one submission.xml file."
        self.assertEqual(response.status, 400)
        self.assertIn(failure_text, await response.text())

    @unittest_run_loop
    async def test_correct_schema_types_are_returned(self):
        """Test api endpoint for all schema types."""
        response = await self.client.get("/schemas")
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

    @unittest_run_loop
    async def test_correct_study_schema_are_returned(self):
        """Test api endpoint for study schema types."""
        response = await self.client.get("/schemas/study")
        response_text = await response.text()
        self.assertIn("study", response_text)
        self.assertNotIn("submission", response_text)

    @unittest_run_loop
    async def test_raises_invalid_schema(self):
        """Test api endpoint for study schema types."""
        response = await self.client.get("/schemas/something")
        self.assertEqual(response.status, 404)

    @unittest_run_loop
    async def test_raises_not_found_schema(self):
        """Test api endpoint for study schema types."""
        response = await self.client.get("/schemas/project")
        self.assertEqual(response.status, 400)
        resp_json = await response.json()
        self.assertEqual(resp_json["detail"], "The provided schema type could not be found. (project)")

    @unittest_run_loop
    async def test_submit_object_works(self):
        """Test that submission is handled, XMLOperator is called."""
        files = [("study", "SRP000539.xml")]
        data = self.create_submission_data(files)
        response = await self.client.post("/objects/study", data=data)
        self.assertEqual(response.status, 201)
        self.assertIn(self.test_ega_string, await response.text())
        self.MockedXMLOperator().create_metadata_object.assert_called_once()

    @unittest_run_loop
    async def test_submit_object_works_with_json(self):
        """Test that JSON submission is handled, operator is called."""
        json_req = {
            "centerName": "GEO",
            "alias": "GSE10966",
            "descriptor": {"studyTitle": "Highly", "studyType": "Other"},
        }
        response = await self.client.post("/objects/study", json=json_req)
        self.assertEqual(response.status, 201)
        self.assertIn(self.test_ega_string, await response.text())
        self.MockedOperator().create_metadata_object.assert_called_once()

    @unittest_run_loop
    async def test_submit_object_missing_field_json(self):
        """Test that JSON has missing property."""
        json_req = {"centerName": "GEO", "alias": "GSE10966"}
        response = await self.client.post("/objects/study", json=json_req)
        reason = "Provided input does not seem correct because: " "''descriptor' is a required property'"
        self.assertEqual(response.status, 400)
        self.assertIn(reason, await response.text())

    @unittest_run_loop
    async def test_submit_object_bad_field_json(self):
        """Test that JSON has bad studyType."""
        json_req = {
            "centerName": "GEO",
            "alias": "GSE10966",
            "descriptor": {"studyTitle": "Highly", "studyType": "ceva"},
        }
        response = await self.client.post("/objects/study", json=json_req)
        reason = "Provided input does not seem correct for field: " "'descriptor'"
        self.assertEqual(response.status, 400)
        self.assertIn(reason, await response.text())

    @unittest_run_loop
    async def test_post_object_bad_json(self):
        """Test that post JSON is badly formated."""
        json_req = {
            "centerName": "GEO",
            "alias": "GSE10966",
            "descriptor": {"studyTitle": "Highly", "studyType": "Other"},
        }
        response = await self.client.post("/objects/study", data=json_req)
        reason = "JSON is not correctly formatted. " "See: Expecting value: line 1 column 1"
        self.assertEqual(response.status, 400)
        self.assertIn(reason, await response.text())

    @unittest_run_loop
    async def test_put_object_bad_json(self):
        """Test that put JSON is badly formated."""
        json_req = {
            "centerName": "GEO",
            "alias": "GSE10966",
            "descriptor": {"studyTitle": "Highly", "studyType": "Other"},
        }
        call = "/drafts/study/EGA123456"
        response = await self.client.put(call, data=json_req)
        reason = "JSON is not correctly formatted. " "See: Expecting value: line 1 column 1"
        self.assertEqual(response.status, 400)
        self.assertIn(reason, await response.text())

    @unittest_run_loop
    async def test_patch_object_bad_json(self):
        """Test that patch JSON is badly formated."""
        json_req = {"centerName": "GEO", "alias": "GSE10966"}
        call = "/drafts/study/EGA123456"
        response = await self.client.patch(call, data=json_req)
        reason = "JSON is not correctly formatted. " "See: Expecting value: line 1 column 1"
        self.assertEqual(response.status, 400)
        self.assertIn(reason, await response.text())

    @unittest_run_loop
    async def test_submit_draft_works_with_json(self):
        """Test that draft JSON submission is handled, operator is called."""
        json_req = {
            "centerName": "GEO",
            "alias": "GSE10966",
            "descriptor": {"studyTitle": "Highly", "studyType": "Other"},
        }
        response = await self.client.post("/drafts/study", json=json_req)
        self.assertEqual(response.status, 201)
        self.assertIn(self.test_ega_string, await response.text())
        self.MockedOperator().create_metadata_object.assert_called_once()

    @unittest_run_loop
    async def test_put_draft_works_with_json(self):
        """Test that draft JSON put method is handled, operator is called."""
        json_req = {
            "centerName": "GEO",
            "alias": "GSE10966",
            "descriptor": {"studyTitle": "Highly", "studyType": "Other"},
        }
        call = "/drafts/study/EGA123456"
        response = await self.client.put(call, json=json_req)
        self.assertEqual(response.status, 200)
        self.assertIn(self.test_ega_string, await response.text())
        self.MockedOperator().replace_metadata_object.assert_called_once()

    @unittest_run_loop
    async def test_put_draft_works_with_xml(self):
        """Test that put XML submisssion is handled, XMLOperator is called."""
        files = [("study", "SRP000539.xml")]
        data = self.create_submission_data(files)
        call = "/drafts/study/EGA123456"
        response = await self.client.put(call, data=data)
        self.assertEqual(response.status, 200)
        self.assertIn(self.test_ega_string, await response.text())
        self.MockedXMLOperator().replace_metadata_object.assert_called_once()

    @unittest_run_loop
    async def test_patch_draft_works_with_json(self):
        """Test that draft JSON patch method is handled, operator is called."""
        json_req = {"centerName": "GEO", "alias": "GSE10966"}
        call = "/drafts/study/EGA123456"
        response = await self.client.patch(call, json=json_req)
        self.assertEqual(response.status, 200)
        self.assertIn(self.test_ega_string, await response.text())
        self.MockedOperator().update_metadata_object.assert_called_once()

    @unittest_run_loop
    async def test_patch_draft_raises_with_xml(self):
        """Test that patch XML submisssion raises error."""
        files = [("study", "SRP000539.xml")]
        data = self.create_submission_data(files)
        call = "/drafts/study/EGA123456"
        response = await self.client.patch(call, data=data)
        self.assertEqual(response.status, 415)

    @unittest_run_loop
    async def test_submit_object_fails_with_too_many_files(self):
        """Test that sending two files to endpoint results failure."""
        files = [("study", "SRP000539.xml"), ("study", "SRP000539_copy.xml")]
        data = self.create_submission_data(files)
        response = await self.client.post("/objects/study", data=data)
        reason = "Only one file can be sent to this endpoint at a time."
        self.assertEqual(response.status, 400)
        self.assertIn(reason, await response.text())

    @unittest_run_loop
    async def test_get_object(self):
        """Test that accessionId returns correct JSON object."""
        url = f"/objects/study/{self.query_accessionId}"
        response = await self.client.get(url)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, "application/json")
        self.assertEqual(self.metadata_json, await response.json())

    @unittest_run_loop
    async def test_get_draft_object(self):
        """Test that draft accessionId returns correct JSON object."""
        url = f"/drafts/study/{self.query_accessionId}"
        response = await self.client.get(url)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, "application/json")
        self.assertEqual(self.metadata_json, await response.json())

    @unittest_run_loop
    async def test_get_object_as_xml(self):
        """Test that accessionId  with XML query returns XML object."""
        url = f"/objects/study/{self.query_accessionId}"
        response = await self.client.get(f"{url}?format=xml")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, "text/xml")
        self.assertEqual(self.metadata_xml, await response.text())

    @unittest_run_loop
    async def test_query_is_called_and_returns_json_in_correct_format(self):
        """Test query method calls operator and returns mocked JSON object."""
        url = f"/objects/study?studyType=foo&name=bar&page={self.page_num}" f"&per_page={self.page_size}"
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

    @unittest_run_loop
    async def test_delete_is_called(self):
        """Test query method calls operator and returns status correctly."""
        url = "/objects/study/EGA123456"
        response = await self.client.delete(url)
        self.assertEqual(response.status, 204)
        self.MockedOperator().delete_metadata_object.assert_called_once()

    @unittest_run_loop
    async def test_query_fails_with_xml_format(self):
        """Test query method calls operator and returns status correctly."""
        url = "/objects/study?studyType=foo&name=bar&format=xml"
        response = await self.client.get(url)
        json_resp = await response.json()
        self.assertEqual(response.status, 400)
        self.assertIn("xml-formatted query results are not supported", json_resp["detail"])

    @unittest_run_loop
    async def test_validation_passes_for_valid_xml(self):
        """Test validation endpoint for valid xml."""
        files = [("study", "SRP000539.xml")]
        data = self.create_submission_data(files)
        response = await self.client.post("/validate", data=data)
        self.assertEqual(response.status, 200)
        self.assertIn('{"isValid":true}', await response.text())

    @unittest_run_loop
    async def test_validation_fails_bad_schema(self):
        """Test validation fails for bad schema and valid xml."""
        files = [("fake", "SRP000539.xml")]
        data = self.create_submission_data(files)
        response = await self.client.post("/validate", data=data)
        self.assertEqual(response.status, 404)

    @unittest_run_loop
    async def test_validation_fails_for_invalid_xml_syntax(self):
        """Test validation endpoint for XML with bad syntax."""
        files = [("study", "SRP000539_invalid.xml")]
        data = self.create_submission_data(files)
        response = await self.client.post("/validate", data=data)
        resp_dict = await response.json()
        self.assertEqual(response.status, 200)
        self.assertIn("Faulty XML file was given, mismatched tag", resp_dict["detail"]["reason"])

    @unittest_run_loop
    async def test_validation_fails_for_invalid_xml(self):
        """Test validation endpoint for invalid xml."""
        files = [("study", "SRP000539_invalid2.xml")]
        data = self.create_submission_data(files)
        response = await self.client.post("/validate", data=data)
        resp_dict = await response.json()
        self.assertEqual(response.status, 200)
        self.assertIn("value must be one of", resp_dict["detail"]["reason"])

    @unittest_run_loop
    async def test_validation_fails_with_too_many_files(self):
        """Test validation endpoint for too many files."""
        files = [("submission", "ERA521986_valid.xml"), ("submission", "ERA521986_valid2.xml")]
        data = self.create_submission_data(files)
        response = await self.client.post("/validate", data=data)
        reason = "Only one file can be sent to this endpoint at a time."
        self.assertEqual(response.status, 400)
        self.assertIn(reason, await response.text())

    @unittest_run_loop
    async def test_operations_fail_for_wrong_schema_type(self):
        """Test 404 error is raised if incorrect schema name is given."""
        get_resp = await self.client.get("/objects/bad_scehma_name/some_id")
        self.assertEqual(get_resp.status, 404)
        json_get_resp = await get_resp.json()
        self.assertIn("Specified schema", json_get_resp["detail"])

        post_rep = await self.client.post("/objects/bad_scehma_name")
        self.assertEqual(post_rep.status, 404)
        post_json_rep = await post_rep.json()
        self.assertIn("Specified schema", post_json_rep["detail"])

        get_resp = await self.client.get("/objects/bad_scehma_name")
        self.assertEqual(get_resp.status, 404)
        json_get_resp = await get_resp.json()
        self.assertIn("Specified schema", json_get_resp["detail"])

        get_resp = await self.client.delete("/objects/bad_scehma_name/some_id")
        self.assertEqual(get_resp.status, 404)
        json_get_resp = await get_resp.json()
        self.assertIn("Specified schema", json_get_resp["detail"])

        get_resp = await self.client.delete("/drafts/bad_scehma_name/some_id")
        self.assertEqual(get_resp.status, 404)
        json_get_resp = await get_resp.json()
        self.assertIn("Specified schema", json_get_resp["detail"])

    @unittest_run_loop
    async def test_query_with_invalid_pagination_params(self):
        """Test that 400s are raised correctly with pagination."""
        get_resp = await self.client.get("/objects/study?page=2?title=joo")
        self.assertEqual(get_resp.status, 400)
        get_resp = await self.client.get("/objects/study?page=0")
        self.assertEqual(get_resp.status, 400)
        get_resp = await self.client.get("/objects/study?per_page=0")
        self.assertEqual(get_resp.status, 400)

    @unittest_run_loop
    async def test_folder_creation_works(self):
        """Test that folder is created and folder ID returned."""
        json_req = {"name": "test", "description": "test folder"}
        response = await self.client.post("/folders", json=json_req)
        json_resp = await response.json()
        self.MockedFolderOperator().create_folder.assert_called_once()
        self.assertEqual(response.status, 201)
        self.assertEqual(json_resp["folderId"], self.folder_id)

    @unittest_run_loop
    async def test_folder_creation_with_missing_data_fails(self):
        """Test that folder creation fails when missing data in request."""
        json_req = {"description": "test folder"}
        response = await self.client.post("/folders", json=json_req)
        json_resp = await response.json()
        self.assertEqual(response.status, 400)
        self.assertIn("'name' is a required property", json_resp["detail"])

    @unittest_run_loop
    async def test_folder_creation_with_empty_body_fails(self):
        """Test that folder creation fails when no data in request."""
        response = await self.client.post("/folders")
        json_resp = await response.json()
        self.assertEqual(response.status, 400)
        self.assertIn("JSON is not correctly formatted.", json_resp["detail"])

    @unittest_run_loop
    async def test_get_folders_with_1_folder(self):
        """Test get_folders() endpoint returns list with 1 folder."""
        self.MockedFolderOperator().query_folders.return_value = (self.test_folder, 1)
        response = await self.client.get("/folders")
        self.MockedFolderOperator().query_folders.assert_called_once()
        self.assertEqual(response.status, 200)
        result = {
            "page": {
                "page": 1,
                "size": 5,
                "totalPages": 1,
                "totalFolders": 1,
            },
            "folders": self.test_folder,
        }
        self.assertEqual(await response.json(), result)

    @unittest_run_loop
    async def test_get_folders_with_no_folders(self):
        """Test get_folders() endpoint returns empty list."""
        self.MockedFolderOperator().query_folders.return_value = ([], 0)
        response = await self.client.get("/folders")
        self.MockedFolderOperator().query_folders.assert_called_once()
        self.assertEqual(response.status, 200)
        result = {
            "page": {
                "page": 1,
                "size": 5,
                "totalPages": 0,
                "totalFolders": 0,
            },
            "folders": [],
        }
        self.assertEqual(await response.json(), result)

    @unittest_run_loop
    async def test_get_folders_with_bad_params(self):
        """Test get_folders() with faulty pagination parameters."""
        response = await self.client.get("/folders?page=ayylmao")
        self.assertEqual(response.status, 400)
        resp = await response.json()
        self.assertEqual(resp["detail"], "page parameter must be a number, now it is ayylmao")

        response = await self.client.get("/folders?page=1&per_page=-100")
        self.assertEqual(response.status, 400)
        resp = await response.json()
        self.assertEqual(resp["detail"], "per_page parameter must be over 0")

        response = await self.client.get("/folders?published=yes")
        self.assertEqual(response.status, 400)
        resp = await response.json()
        self.assertEqual(resp["detail"], "'published' parameter must be either 'true' or 'false'")

    @unittest_run_loop
    async def test_get_folder_works(self):
        """Test folder is returned when correct folder id is given."""
        response = await self.client.get("/folders/FOL12345678")
        self.assertEqual(response.status, 200)
        self.MockedFolderOperator().read_folder.assert_called_once()
        json_resp = await response.json()
        self.assertEqual(self.test_folder, json_resp)

    @unittest_run_loop
    async def test_update_folder_fails_with_wrong_key(self):
        """Test that folder does not update when wrong keys are provided."""
        data = [{"op": "add", "path": "/objects"}]
        response = await self.client.patch("/folders/FOL12345678", json=data)
        self.assertEqual(response.status, 400)
        json_resp = await response.json()
        reason = "Request contains '/objects' key that cannot be " "updated to folders."
        self.assertEqual(reason, json_resp["detail"])

    @unittest_run_loop
    async def test_update_folder_passes(self):
        """Test that folder would update with correct keys."""
        self.MockedFolderOperator().update_folder.return_value = self.folder_id
        data = [{"op": "replace", "path": "/name", "value": "test2"}]
        response = await self.client.patch("/folders/FOL12345678", json=data)
        self.MockedFolderOperator().update_folder.assert_called_once()
        self.assertEqual(response.status, 200)
        json_resp = await response.json()
        self.assertEqual(json_resp["folderId"], self.folder_id)

    @unittest_run_loop
    async def test_folder_is_published(self):
        """Test that folder would be published."""
        self.MockedFolderOperator().update_folder.return_value = self.folder_id
        response = await self.client.patch("/publish/FOL12345678")
        self.MockedFolderOperator().update_folder.assert_called_once()
        self.assertEqual(response.status, 200)
        json_resp = await response.json()
        self.assertEqual(json_resp["folderId"], self.folder_id)

    @unittest_run_loop
    async def test_folder_deletion_is_called(self):
        """Test that folder would be deleted."""
        self.MockedFolderOperator().read_folder.return_value = self.test_folder
        response = await self.client.delete("/folders/FOL12345678")
        self.MockedFolderOperator().read_folder.assert_called_once()
        self.MockedFolderOperator().delete_folder.assert_called_once()
        self.assertEqual(response.status, 204)

    @unittest_run_loop
    async def test_get_user_works(self):
        """Test user object is returned when correct user id is given."""
        response = await self.client.get("/users/current")
        self.assertEqual(response.status, 200)
        self.MockedUserOperator().read_user.assert_called_once()
        json_resp = await response.json()
        self.assertEqual(self.test_user, json_resp)

    @unittest_run_loop
    async def test_get_user_drafts_with_no_drafts(self):
        """Test getting user drafts when user has no drafts."""
        response = await self.client.get("/users/current?items=drafts")
        self.assertEqual(response.status, 200)
        self.MockedUserOperator().filter_user.assert_called_once()
        json_resp = await response.json()
        result = {
            "page": {
                "page": 1,
                "size": 5,
                "totalPages": 0,
                "totalDrafts": 0,
            },
            "drafts": [],
        }
        self.assertEqual(json_resp, result)

    @unittest_run_loop
    async def test_get_user_drafts_with_1_draft(self):
        """Test getting user drafts when user has 1 draft."""
        user = self.test_user
        user["drafts"].append(self.metadata_json)
        self.MockedUserOperator().filter_user.return_value = (user["drafts"], 1)
        response = await self.client.get("/users/current?items=drafts")
        self.assertEqual(response.status, 200)
        self.MockedUserOperator().filter_user.assert_called_once()
        json_resp = await response.json()
        result = {
            "page": {
                "page": 1,
                "size": 5,
                "totalPages": 1,
                "totalDrafts": 1,
            },
            "drafts": [self.metadata_json],
        }
        self.assertEqual(json_resp, result)

    @unittest_run_loop
    async def test_get_user_folder_list(self):
        """Test get user with folders url returns a folder ID."""
        self.MockedUserOperator().filter_user.return_value = (self.test_user["folders"], 1)
        response = await self.client.get("/users/current?items=folders")
        self.assertEqual(response.status, 200)
        self.MockedUserOperator().filter_user.assert_called_once()
        json_resp = await response.json()
        result = {
            "page": {
                "page": 1,
                "size": 5,
                "totalPages": 1,
                "totalFolders": 1,
            },
            "folders": ["FOL12345678"],
        }
        self.assertEqual(json_resp, result)

    @unittest_run_loop
    async def test_get_user_items_with_bad_param(self):
        """Test that error is raised if items parameter in query is not drafts or folders."""
        response = await self.client.get("/users/current?items=wrong_thing")
        self.assertEqual(response.status, 400)
        json_resp = await response.json()
        self.assertEqual(
            json_resp["detail"], "wrong_thing is a faulty item parameter. Should be either folders or drafts"
        )

    @unittest_run_loop
    async def test_user_deletion_is_called(self):
        """Test that user object would be deleted."""
        self.MockedUserOperator().read_user.return_value = self.test_user
        self.MockedUserOperator().delete_user.return_value = None
        await self.client.delete("/users/current")
        self.MockedUserOperator().read_user.assert_called_once()
        self.MockedUserOperator().delete_user.assert_called_once()

    @unittest_run_loop
    async def test_update_user_fails_with_wrong_key(self):
        """Test that user object does not update when forbidden keys are provided."""
        data = [{"op": "add", "path": "/userId"}]
        response = await self.client.patch("/users/current", json=data)
        self.assertEqual(response.status, 400)
        json_resp = await response.json()
        reason = "Request contains '/userId' key that cannot be updated to user object"
        self.assertEqual(reason, json_resp["detail"])

    @unittest_run_loop
    async def test_update_user_passes(self):
        """Test that user object would update with correct keys."""
        self.MockedUserOperator().update_user.return_value = self.user_id
        data = [{"op": "add", "path": "/drafts/-", "value": [{"accessionId": "3", "schema": "sample"}]}]
        response = await self.client.patch("/users/current", json=data)
        self.MockedUserOperator().update_user.assert_called_once()
        self.assertEqual(response.status, 200)
        json_resp = await response.json()
        self.assertEqual(json_resp["userId"], self.user_id)
