"""Test api endpoints from views module."""

from pathlib import Path
from unittest.mock import patch

from aiohttp import FormData, web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from aiounittest import futurized

from metadata_backend.helpers.schema_loader import SchemaNotFoundException
from metadata_backend.server import init
from tests.test_operators import MockCursor


class HandlersTestCase(AioHTTPTestCase):
    """Api endpoint class test cases."""

    TESTFILES_ROOT = Path(__file__).parent / 'test_files'

    async def get_application(self):
        """Retrieve web Application for test."""
        return await init()

    async def setUpAsync(self):
        """Configure default values for testing and other modules.

        This patches used modules and sets default return values for their
        methods. Also sets up reusable test variables for different test
        methods.
        """
        self.test_ega_string = "EGA123456"
        self.query_accessionId = "EDAG3991701442770179",
        self.page_num = 3
        self.page_size = 50
        self.total_objects = 150
        self.metadata_json = {"study": {
            "attributes": {
                "centerName": "GEO",
                "alias": "GSE10966",
                "accession": "SRP000539"
            },
            "accessionId": "EDAG3991701442770179", }
        }
        path_to_xml_file = self.TESTFILES_ROOT / "study" / "SRP000539.xml"
        self.metadata_xml = path_to_xml_file.read_text()
        self.accession_id = "EGA123456"
        self.folder_id = "FOL12345678"

        class_parser = "metadata_backend.api.handlers.XMLToJSONParser"
        class_operator = "metadata_backend.api.handlers.Operator"
        class_xmloperator = "metadata_backend.api.handlers.XMLOperator"
        class_dbservice = "metadata_backend.api.handlers.DBService"
        operator_config = {'read_metadata_object.side_effect':
                           self.fake_operator_read_metadata_object,
                           'query_metadata_database.side_effect':
                           self.fake_operator_query_metadata_object,
                           'create_metadata_object.side_effect':
                           self.fake_operator_create_metadata_object,
                           'delete_metadata_object.side_effect':
                           self.fake_operator_delete_metadata_object,
                           }
        xmloperator_config = {'read_metadata_object.side_effect':
                              self.fake_xmloperator_read_metadata_object,
                              'create_metadata_object.side_effect':
                              self.fake_xmloperator_create_metadata_object,
                              }
        self.patch_parser = patch(class_parser, spec=True)
        self.patch_operator = patch(class_operator, **operator_config,
                                    spec=True)
        self.patch_xmloperator = patch(class_xmloperator, **xmloperator_config,
                                       spec=True)
        self.patch_dbservice = patch(class_dbservice, spec=True)
        self.patch_folder = patch(
            "metadata_backend.api.handlers.RESTApiHandler._generate_folder_id",
            return_value=self.folder_id,
            autospec=True)
        self.MockedParser = self.patch_parser.start()
        self.MockedOperator = self.patch_operator.start()
        self.MockedXMLOperator = self.patch_xmloperator.start()
        self.MockedDbService = self.patch_dbservice.start()
        self.patch_folder.start()

    async def tearDownAsync(self):
        """Cleanup mocked stuff."""
        self.patch_parser.stop()
        self.patch_operator.stop()
        self.patch_xmloperator.stop()
        self.patch_dbservice.stop()
        self.patch_folder.stop()

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

    async def fake_operator_read_metadata_object(self, schema_type,
                                                 accession_id):
        """Fake read operation to return mocked json."""
        return await futurized((self.metadata_json, "application/json"))

    async def fake_operator_query_metadata_object(self, schema_type, query,
                                                  page_num, page_size):
        """Fake query operation to return list containing mocked json."""
        return await futurized(([self.metadata_json], self.page_num,
                               self.page_size, self.total_objects),)

    async def fake_xmloperator_read_metadata_object(self, schema_type,
                                                    accession_id):
        """Fake read operation to return mocked xml."""
        return await futurized((self.metadata_xml, "text/xml"))

    async def fake_xmloperator_create_metadata_object(self, schema_type,
                                                      content):
        """Fake create operation to return mocked accessionId."""
        return await futurized(self.test_ega_string)

    async def fake_operator_create_metadata_object(self, schema_type, content):
        """Fake create operation to return mocked accessionId."""
        return await futurized(self.test_ega_string)

    async def fake_operator_delete_metadata_object(self, schema_type,
                                                   accession_id):
        """Fake delete operation to await nothing."""
        return await futurized(None)

    @unittest_run_loop
    async def test_submit_endpoint_submission_does_not_fail(self):
        """Test that submission with valid SUBMISSION.xml does not fail."""
        files = [("submission", "ERA521986_valid.xml")]
        data = self.create_submission_data(files)
        response = await self.client.post("/submit", data=data)
        self.assertEqual(response.status, 201)
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
        files = [("submission", "ERA521986_valid.xml"),
                 ("submission", "ERA521986_valid2.xml")]
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
        schema_types = ["submission", "study", "sample", "experiment", "run",
                        "analysis", "dac", "policy", "dataset", "project"]
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
        await self.client.get("/schemas/something")
        self.assertRaises(web.HTTPNotFound)

    @unittest_run_loop
    async def test_raises_not_found_schema(self):
        """Test api endpoint for study schema types."""
        await self.client.get("/schemas/project")
        self.assertRaises(SchemaNotFoundException)

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
        """Test that json submission is handled, operator is called."""
        json_req = {"centerName": "GEO",
                    "alias": "GSE10966",
                    "descriptor": {"studyTitle": "Highly",
                                   "studyType": "Other"}}
        response = await self.client.post("/objects/study", json=json_req)
        self.assertEqual(response.status, 201)
        self.assertIn(self.test_ega_string, await response.text())
        self.MockedOperator().create_metadata_object.assert_called_once()

    @unittest_run_loop
    async def test_submit_draft_works_with_json(self):
        """Test that draft json submission is handled, operator is called."""
        json_req = {"centerName": "GEO",
                    "alias": "GSE10966",
                    "descriptor": {"studyTitle": "Highly",
                                   "studyType": "Other"}}
        response = await self.client.post("/drafts/study", json=json_req)
        self.assertEqual(response.status, 201)
        self.assertIn(self.test_ega_string, await response.text())
        self.MockedOperator().create_metadata_object.assert_called_once()

    @unittest_run_loop
    async def test_put_draft_works_with_json(self):
        """Test that draft json put method is handled, operator is called."""
        json_req = {"centerName": "GEO",
                    "alias": "GSE10966",
                    "descriptor": {"studyTitle": "Highly",
                                   "studyType": "Other"}}
        call = "/drafts/study/EGA123456"
        response = await self.client.put(call, json=json_req)
        self.assertEqual(response.status, 201)
        self.assertIn(self.test_ega_string, await response.text())
        self.MockedOperator().replace_metadata_object.assert_called_once()

    @unittest_run_loop
    async def test_put_draft_works_with_xml(self):
        """Test that put XML submisssion is handled, XMLOperator is called."""
        files = [("study", "SRP000539.xml")]
        data = self.create_submission_data(files)
        call = "/drafts/study/EGA123456"
        response = await self.client.put(call, data=data)
        self.assertEqual(response.status, 201)
        self.assertIn(self.test_ega_string, await response.text())
        self.MockedXMLOperator().replace_metadata_object.assert_called_once()

    @unittest_run_loop
    async def test_patch_draft_works_with_json(self):
        """Test that draft json patch method is handled, operator is called."""
        json_req = {"centerName": "GEO",
                    "alias": "GSE10966"}
        call = "/drafts/study/EGA123456"
        response = await self.client.patch(call, json=json_req)
        self.assertEqual(response.status, 201)
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
        files = [("study", "SRP000539.xml"),
                 ("study", "SRP000539_copy.xml")]
        data = self.create_submission_data(files)
        response = await self.client.post("/objects/study", data=data)
        reason = "Only one file can be sent to this endpoint at a time."
        self.assertEqual(response.status, 400)
        self.assertIn(reason, await response.text())

    @unittest_run_loop
    async def test_get_object(self):
        """Test that accessionId returns correct json object."""
        url = f"/objects/study/{self.query_accessionId}"
        response = await self.client.get(url)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, "application/json")
        self.assertEqual(self.metadata_json, await response.json())

    @unittest_run_loop
    async def test_get_draft_object(self):
        """Test that draft accessionId returns correct json object."""
        url = f"/drafts/study/{self.query_accessionId}"
        response = await self.client.get(url)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, "application/json")
        self.assertEqual(self.metadata_json, await response.json())

    @unittest_run_loop
    async def test_get_object_as_xml(self):
        """Test that accessionId  with xml query returns xml object."""
        url = f"/objects/study/{self.query_accessionId}"
        response = await self.client.get(f"{url}?format=xml")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, "text/xml")
        self.assertEqual(self.metadata_xml, await response.text())

    @unittest_run_loop
    async def test_query_is_called_and_returns_json_in_correct_format(self):
        """Test query method calls operator and returns mocked json object."""
        url = (f"/objects/study?studyType=foo&name=bar&page={self.page_num}"
               f"&per_page={self.page_size}")
        response = await self.client.get(url)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, "application/json")
        json_resp = await response.json()
        self.assertEqual(json_resp["page"]["page"], self.page_num)
        self.assertEqual(json_resp["page"]["size"], self.page_size)
        self.assertEqual(json_resp["page"]["totalPages"], (self.total_objects
                                                           / self.page_size))
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
        self.assertIn("xml-formatted query results are not supported",
                      json_resp["detail"])

    @unittest_run_loop
    async def test_validation_passes_for_valid_xml(self):
        """Test validation endpoint for valid xml."""
        files = [("study", "SRP000539.xml")]
        data = self.create_submission_data(files)
        response = await self.client.post("/validate", data=data)
        self.assertEqual(response.status, 200)
        self.assertIn('{"isValid": true}', await response.text())

    @unittest_run_loop
    async def test_validation_fails_for_invalid_xml_syntax(self):
        """Test validation endpoint for xml with bad syntax."""
        files = [("study", "SRP000539_invalid.xml")]
        data = self.create_submission_data(files)
        response = await self.client.post("/validate", data=data)
        resp_dict = await response.json()
        self.assertEqual(response.status, 200)
        self.assertIn("Faulty XML file was given, mismatched tag",
                      resp_dict['detail']['reason'])

    @unittest_run_loop
    async def test_validation_fails_for_invalid_xml(self):
        """Test validation endpoint for invalid xml."""
        files = [("study", "SRP000539_invalid2.xml")]
        data = self.create_submission_data(files)
        response = await self.client.post("/validate", data=data)
        resp_dict = await response.json()
        self.assertEqual(response.status, 200)
        self.assertIn("invalid value", resp_dict['detail']['reason'])

    @unittest_run_loop
    async def test_validation_fails_with_too_many_files(self):
        """Test validation endpoint for too many files."""
        files = [("submission", "ERA521986_valid.xml"),
                 ("submission", "ERA521986_valid2.xml")]
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
        self.assertIn("Specified schema", json_get_resp['detail'])

        post_rep = await self.client.post("/objects/bad_scehma_name")
        self.assertEqual(post_rep.status, 404)
        post_json_rep = await post_rep.json()
        self.assertIn("Specified schema", post_json_rep['detail'])

        get_resp = await self.client.get("/objects/bad_scehma_name")
        self.assertEqual(get_resp.status, 404)
        json_get_resp = await get_resp.json()
        self.assertIn("Specified schema", json_get_resp['detail'])

        get_resp = await self.client.delete("/objects/bad_scehma_name/some_id")
        self.assertEqual(get_resp.status, 404)
        json_get_resp = await get_resp.json()
        self.assertIn("Specified schema", json_get_resp['detail'])

        get_resp = await self.client.delete("/drafts/bad_scehma_name/some_id")
        self.assertEqual(get_resp.status, 404)
        json_get_resp = await get_resp.json()
        self.assertIn("Specified schema", json_get_resp['detail'])

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
        self.MockedDbService().create.return_value = futurized(True)
        json_req = {"name": "test",
                    "description": "test folder"}
        response = await self.client.post("/folders", json=json_req)
        json_resp = await response.json()
        self.MockedDbService().create.assert_called_once()
        self.assertEqual(response.status, 201)
        self.assertEqual(json_resp['folderId'], self.folder_id)

    @unittest_run_loop
    async def test_folder_creation_with_empty_body(self):
        """Test that folder creation fails when no data in request."""
        response = await self.client.post("/folders")
        json_resp = await response.json()
        self.assertEqual(response.status, 400)
        self.assertIn("JSON is not correctly formatted.", json_resp['detail'])

    @unittest_run_loop
    async def test_get_folders_with_1_folder(self):
        """Test get_folders() endpoint returns list with 1 folder."""
        folder = [{"_id": {"$oid": "5ecd28877f55c72e263f45c2"},
                   "folderId": self.folder_id,
                   "name": "test",
                   "description": "test folder",
                   "metadata_objects": []}]
        self.MockedDbService().query.return_value = MockCursor(folder)
        response = await self.client.get("/folders")
        self.MockedDbService().query.assert_called_once()
        self.assertEqual(response.status, 200)
        self.assertEqual(await response.json(), {'folders': folder})

    @unittest_run_loop
    async def test_get_folders_with_no_folders(self):
        """Test get_folders() endpoint returns empty list."""
        self.MockedDbService().query.return_value = MockCursor({})
        response = await self.client.get("/folders")
        self.MockedDbService().query.assert_called_once()
        self.assertEqual(response.status, 200)
        self.assertEqual(await response.json(), {'folders': []})

    @unittest_run_loop
    async def test_get_folder_fails(self):
        """Test 404 error is raised if incorrect folder id is given."""
        response = await self.client.get("/folders/some_id")
        self.assertEqual(response.status, 404)
        json_resp = await response.json()
        self.assertEqual("Folder with id some_id not found.",
                         json_resp['detail'])

    @unittest_run_loop
    async def test_get_folder_works(self):
        """Test folder is returned when correct folder id is given."""
        folder = {"_id": {"$oid": "5ecd28877f55c72e263f45c2"},
                  "folderId": self.folder_id,
                  "name": "test",
                  "description": "test folder",
                  "metadata_objects": []}
        self.MockedDbService().read.return_value = futurized(folder)
        response = await self.client.get("/folders/FOL12345678")
        self.MockedDbService().read.assert_called_once()
        self.assertEqual(response.status, 200)
        json_resp = await response.json()
        self.assertEqual(folder, json_resp)
