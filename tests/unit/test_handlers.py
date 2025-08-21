"""Test API endpoints from handlers module."""

import json
import os
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
import ujson
from aiohttp import FormData, web
from aiohttp.test_utils import AioHTTPTestCase, make_mocked_coro
from aiohttp.web import Request
from defusedxml import ElementTree

from metadata_backend.api.handlers.restapi import RESTAPIHandler
from metadata_backend.api.models import Object, Project, Registration, Rems, SubmissionWorkflow, User
from metadata_backend.api.services.auth import ApiKey
from metadata_backend.api.services.file import FileProviderService
from metadata_backend.api.services.project import ProjectService
from metadata_backend.conf.conf import API_PREFIX, get_workflow
from metadata_backend.database.postgres.models import FileEntity
from metadata_backend.database.postgres.repositories.file import FileRepository
from metadata_backend.database.postgres.repositories.object import ObjectRepository
from metadata_backend.database.postgres.repositories.submission import (
    SUB_FIELD_DOI,
    SUB_FIELD_REMS,
    SubmissionRepository,
)
from metadata_backend.database.postgres.repository import transaction
from metadata_backend.server import init
from metadata_backend.services.rems_service_handler import RemsServiceHandler

from .conftest import _session_factory
from .database.postgres.helpers import create_object_entity, create_submission_entity


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
        self.patch_verify_user_project = patch.object(
            ProjectService, "verify_user_project", new=AsyncMock(return_value=True)
        )
        self.patch_verify_user_project_failure = patch.object(
            ProjectService,
            "verify_user_project",
            new=AsyncMock(side_effect=web.HTTPUnauthorized(reason="Mocked unauthorized access")),
        )

        # Mock REMS license verification.
        self.patch_verify_rems_workflow_licence = patch(
            "metadata_backend.services.rems_service_handler.RemsServiceHandler.validate_workflow_licenses",
            return_value=True,
        )

        await self.client.start_server()

        self.test_ega_string = "EGA123456"
        self.query_accessionId = ("EDAG3991701442770179",)
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
        self.doi_info = {
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
        }
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
            "doiInfo": self.doi_info,
            "files": [{"accessionId": "file1", "version": 1, "status": "added"}],
        }
        self.user_id = "USR12345678"
        self.test_user = {
            "userId": self.user_id,
            "name": "tester",
        }
        self.projected_file_example = {
            "filepath": "bucketname/file1",
            "status": "added",
            "encrypted_checksums": [
                {"type": "sha256", "value": "82E4e60e73db2e06A00a079788F7d71f75b61a4b75f28c4c9427036d6"},
                {"type": "md5", "value": "7Ac236b1a82dac89e7cf45d2b48"},
            ],
            "unencrypted_checksums": [
                {"type": "sha256", "value": "82E4e60e73db2e06A00a079788F7d71f75b61a4b75f28c4c9427036d6"},
                {"type": "md5", "value": "7Ac236b1a82dac89e7cf45d2b48"},
            ],
            "objectId": {
                "accessionId": "EGA123456",
                "schema": "run",
            },
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

        RESTAPIHandler.check_ownership = make_mocked_coro(True)

        def mocked_get_param(self, req: Request, name: str) -> str:
            if name == "projectId" and "projectId" not in req.query:
                return "mock-project"

            param = req.query.get(name, "")
            if param == "":
                raise web.HTTPBadRequest(reason=f"mandatory query parameter {name} is not set")
            return param

        RESTAPIHandler._get_param = mocked_get_param

    async def tearDownAsync(self):
        """Cleanup mocked stuff."""
        await self.client.close()

    def read_metadata_object(self, schema: str, file_name: str) -> str:
        """Read metadata object from file."""
        file_path = self.TESTFILES_ROOT / schema / file_name
        with open(file_path.as_posix(), "r", encoding="utf-8") as f:
            return f.read()

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

    async def fake_get_submission_field_str(self, submission_id, field):
        """Fake get submission field."""
        if field == "workflow":
            return "FEGA"
        elif field == "projectId":
            return self.project_id
        return ""

    async def fake_read_submission_files(self, submission_id, status_list):
        """Fake read submission files."""
        return [self.projected_file_example]

    async def fake_check_submission_files(self, submission_id):
        """Fake check submission files."""
        return True, []

    async def post_submission(
        self,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        project_id: str | None = None,
        workflow: str = "SDSX",
    ) -> str:
        """Post a submission."""

        if name is None:
            name = f"name_{uuid.uuid4()}"
        if title is None:
            title = f"title_{uuid.uuid4()}"
        if description is None:
            description = f"description_{uuid.uuid4()}"
        if project_id is None:
            project_id = f"project_{uuid.uuid4()}"

        with (
            self.patch_verify_authorization,
            self.patch_verify_user_project,
        ):
            data = {
                "name": name,
                "title": title,
                "description": description,
                "projectId": project_id,
                "workflow": workflow,
            }
            response = await self.client.post(f"{API_PREFIX}/submissions", json=data)
            response.raise_for_status()
            return (await response.json())["submissionId"]

    async def get_submission(self, submission_id) -> dict[str, Any]:
        """Get a submission."""
        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):
            response = await self.client.get(f"{API_PREFIX}/submissions/{submission_id}")
            response.raise_for_status()
            return await response.json()


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
                resp_json["detail"], "The provided schema type could not be found. Occurred for JSON schema: 'project'."
            )

    async def test_get_schema_submission(self):
        """Test API endpoint for submission schema type."""
        with self.patch_verify_authorization:
            response = await self.client.get(f"{API_PREFIX}/schemas/submission")
            self.assertEqual(response.status, 200)
            resp_json = await response.json()
            assert resp_json["$schema"] == "https://json-schema.org/draft/2020-12/schema"
            assert resp_json["description"] == "Submission that contains submitted metadata objects"


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


class ObjectHandlerTestCase(HandlersTestCase):
    """Object API endpoint class test cases."""

    @staticmethod
    def assert_xml(expected: str, actual: str, remove_attr_xpath: tuple[str, str] | None = None) -> None:
        def clean_xml(xml_str):
            root = ElementTree.fromstring(xml_str)

            # Remove xmlns* attributes
            for elem in root.iter():
                elem.attrib = {k: v for k, v in elem.attrib.items() if not k.startswith("xmlns")}

            # Remove specific attribute at a given XPath
            if remove_attr_xpath:
                xpath, attr_name = remove_attr_xpath
                for target in root.findall(xpath):
                    if attr_name in target.attrib:
                        del target.attrib[attr_name]

            return root

        cleaned_expected = ElementTree.tostring(clean_xml(expected))
        cleaned_actual = ElementTree.tostring(clean_xml(actual))

        assert cleaned_expected == cleaned_actual

    @staticmethod
    def change_xml_attribute(xml: str, xpath: str, attribute: str, new_value: str) -> str:
        root = ElementTree.fromstring(xml)
        for elem in root.findall(xpath):
            if attribute in elem.attrib:
                elem.attrib[attribute] = new_value
        return ElementTree.tostring(root, encoding="unicode")

    async def test_post_get_delete_xml_object(self):
        """Test that creating, modifying and deleting XML metadata object works."""

        bp_files = [
            ("bpannotation", "annotation.xml", (".//ANNOTATION", "alias"), (".//ANNOTATION", "accession")),
            ("bpobservation", "observation.xml", (".//OBSERVATION", "alias"), (".//OBSERVATION", "accession")),
            # TODO(improve): test all BP XML files
        ]

        fega_files = [
            ("policy", "policy.xml", (".//POLICY", "alias"), (".//POLICY", "accession")),
            # TODO(improve): test all FEGA XML files
        ]

        workflow_files = {
            SubmissionWorkflow.BP: bp_files,
            SubmissionWorkflow.FEGA: fega_files,
        }

        for workflow in {SubmissionWorkflow.BP, SubmissionWorkflow.FEGA}:
            submission_id = await self.post_submission(workflow=workflow.value)

            files = workflow_files[workflow]

            with (
                self.patch_verify_user_project,
                self.patch_verify_authorization,
            ):
                for schema, file_name, alias_xpath, accession_xpath in files:
                    xml_document = self.read_metadata_object(schema, file_name)

                    alias = f"alias-{uuid.uuid4()}"
                    xml_document = self.change_xml_attribute(xml_document, *alias_xpath, alias)

                    # Create metadata object with content type auto-detection.

                    response = await self.client.post(
                        f"{API_PREFIX}/objects/{schema}", params={"submission": submission_id}, data=xml_document
                    )
                    assert response.status == 201
                    result = await response.json()
                    assert result[0]["alias"] == alias
                    assert "accessionId" in result[0]

                    accession_id = result[0]["accessionId"]

                    # Read metadata object as xml.

                    response = await self.client.get(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}",
                        headers={"Content-Type": "application/xml"},
                        data=xml_document,
                    )
                    assert response.status == 200
                    self.assert_xml(xml_document, await response.text(), accession_xpath)

                    # Read metadata object as json.

                    response = await self.client.get(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}",
                        headers={"Content-Type": "application/json"},
                    )
                    assert response.status == 200
                    assert (await response.json())["accessionId"] == accession_id

                    # Read metadata object as json (default content type).

                    response = await self.client.get(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}",
                    )
                    assert response.status == 200
                    assert (await response.json())["accessionId"] == accession_id

                    # Read metadata object ids.

                    response = await self.client.get(f"{API_PREFIX}/objects/{schema}?submission={submission_id}")
                    assert response.status == 200
                    assert Object(object_id=accession_id, submission_id=submission_id, schema_type=schema) == Object(
                        **(await response.json())[0]
                    )

                    # Update metadata object (put) without content type auto-detection.

                    alias = f"alias-{uuid.uuid4()}"  # Changing alias as its updated is allowed.
                    xml_document = self.change_xml_attribute(xml_document, *alias_xpath, alias)

                    response = await self.client.put(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}",
                        headers={"Content-Type": "application/xml"},
                        data=xml_document,
                    )
                    assert response.status == 200
                    result = await response.json()
                    assert result["accessionId"] == accession_id

                    # Read metadata object as xml.

                    response = await self.client.get(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}",
                        headers={"Content-Type": "application/xml"},
                    )
                    assert response.status == 200
                    self.assert_xml(xml_document, await response.text(), accession_xpath)

                    # Update metadata object (patch) with content type auto-detection.

                    alias = f"alias-{uuid.uuid4()}"  # Changing alias as its updated is allowed.
                    xml_document = self.change_xml_attribute(xml_document, *alias_xpath, alias)

                    response = await self.client.patch(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}", data=xml_document
                    )
                    assert response.status == 200
                    result = await response.json()
                    assert result["accessionId"] == accession_id

                    # Read metadata object as xml.

                    response = await self.client.get(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}",
                        headers={"Content-Type": "application/xml"},
                    )
                    assert response.status == 200
                    self.assert_xml(xml_document, await response.text(), accession_xpath)

                    # Delete metadata object

                    response = await self.client.delete(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}",
                    )
                    assert response.status == 204

                    # Read metadata object.

                    response = await self.client.get(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}",
                    )
                    assert response.status == 404

    async def test_post_get_delete_json_object(self):
        """Test that creating, modifying and deleting JSON metadata object works."""

        bp_files = [
            ("bpannotation", "annotation.json"),
            ("bpobserver", "observer.json"),
            # TODO(improve): test all BP JSON files
        ]

        fega_files = [
            ("dataset", "dataset.json"),
            # TODO(improve): test all FEGA JSON files
        ]

        workflow_files = {
            SubmissionWorkflow.BP: bp_files,
            SubmissionWorkflow.FEGA: fega_files,
        }

        alias_callback = lambda d, val: {**d, "alias": val}

        def update_json_field(json_str: str, val: str, update_callback: Callable[[dict, str], dict]) -> str:
            return json.dumps(update_callback(json.loads(json_str), val))

        for workflow in {SubmissionWorkflow.BP, SubmissionWorkflow.FEGA}:
            submission_id = await self.post_submission(workflow=workflow.value)

            files = workflow_files[workflow]

            with (
                self.patch_verify_user_project,
                self.patch_verify_authorization,
            ):
                for schema, file_name in files:
                    json_document = self.read_metadata_object(schema, file_name)

                    alias = f"alias-{uuid.uuid4()}"
                    json_document = update_json_field(json_document, alias, alias_callback)

                    # Create metadata object with content type auto-detection.

                    response = await self.client.post(
                        f"{API_PREFIX}/objects/{schema}", params={"submission": submission_id}, data=json_document
                    )
                    assert response.status == 201
                    result = await response.json()
                    assert result[0]["alias"] == alias
                    assert "accessionId" in result[0]

                    accession_id = result[0]["accessionId"]

                    # Read metadata object as json.

                    response = await self.client.get(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}",
                        headers={"Content-Type": "application/json"},
                    )
                    assert response.status == 200
                    result = await response.json()
                    assert {**json.loads(json_document), "accessionId": accession_id} == result

                    # Read metadata object as json (default content type).

                    response = await self.client.get(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}",
                    )
                    assert response.status == 200
                    result = await response.json()
                    assert {**json.loads(json_document), "accessionId": accession_id} == result

                    # Read metadata object ids.

                    response = await self.client.get(f"{API_PREFIX}/objects/{schema}?submission={submission_id}")
                    assert response.status == 200
                    assert Object(object_id=accession_id, submission_id=submission_id, schema_type=schema) == Object(
                        **(await response.json())[0]
                    )

                    # Update metadata object (put) without content type auto-detection.

                    alias = f"alias-{uuid.uuid4()}"  # Changing alias as its update is allowed.
                    json_document = update_json_field(json_document, alias, alias_callback)

                    response = await self.client.put(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}",
                        headers={"Content-Type": "application/json"},
                        data=json_document,
                    )
                    assert response.status == 200
                    result = await response.json()
                    assert result["accessionId"] == accession_id

                    # Read metadata object as json.

                    response = await self.client.get(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}",
                    )
                    assert response.status == 200
                    result = await response.json()
                    assert {**json.loads(json_document), "accessionId": accession_id} == result

                    # Update metadata object (patch) with content type auto-detection.

                    alias = f"alias-{uuid.uuid4()}"  # Changing alias as its update is allowed.
                    json_document = update_json_field(json_document, alias, alias_callback)

                    response = await self.client.patch(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}", data=json_document
                    )
                    assert response.status == 200
                    result = await response.json()
                    assert result["accessionId"] == accession_id

                    # Read metadata object as json.

                    response = await self.client.get(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}",
                    )
                    assert response.status == 200
                    result = await response.json()
                    assert {**json.loads(json_document), "accessionId": accession_id} == result

                    # Delete metadata object

                    response = await self.client.delete(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}",
                    )
                    assert response.status == 204

                    # Read metadata object.

                    response = await self.client.get(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}",
                    )
                    assert response.status == 404

    async def test_post_invalid_json_object(self):
        """Test posting invalid JSON metadata object."""

        workflow = SubmissionWorkflow.FEGA
        schema = "dataset"
        submission_id = await self.post_submission(workflow=workflow.value)

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):
            response = await self.client.post(
                f"{API_PREFIX}/objects/{schema}", params={"submission": submission_id}, data="invalid"
            )
            assert response.status == 400
            assert "Invalid JSON payload" in await response.text()

    async def test_post_invalid_xml_object(self):
        """Test posting invalid XML metadata object."""

        workflow = SubmissionWorkflow.FEGA
        schema = "dataset"
        submission_id = await self.post_submission(workflow=workflow.value)

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):
            response = await self.client.post(
                f"{API_PREFIX}/objects/{schema}",
                params={"submission": submission_id},
                headers={"Content-Type": "application/xml"},
                data="invalid",
            )
            assert response.status == 400
            assert "not valid" in await response.text()

    async def test_post_invalid_schema(self):
        """Test posting invalid metadata object schema."""

        workflow = SubmissionWorkflow.BP
        schema = "invalid"
        submission_id = await self.post_submission(workflow=workflow.value)

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):
            response = await self.client.post(
                f"{API_PREFIX}/objects/{schema}", params={"submission": submission_id}, data="invalid"
            )
            assert response.status == 400
            assert "does not support" in await response.text()

    async def test_post_bp_xml_rems(self):
        """Test that creating BP REMS XML works."""
        submission_id = await self.post_submission(workflow=SubmissionWorkflow.BP.value)
        schema = "bprems"
        xml_document = self.read_metadata_object(schema, "rems.xml")

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):
            # Post BP REMS.
            response = await self.client.post(
                f"{API_PREFIX}/objects/{schema}", params={"submission": submission_id}, data=xml_document
            )
            self.assertEqual(response.status, 201)

            # Verify that REMS was added to the submission.
            response = await self.client.get(f"{API_PREFIX}/submissions/{submission_id}")
            self.assertEqual(response.status, 200)
            submission = await response.json()
            rems = Rems(**submission["rems"])
            assert rems.workflow_id == 1, "'workflowId' is not 1"
            assert rems.organization_id == "CSC", "'organizationId' is not CSC"
            assert rems.licenses == []


class SubmissionHandlerTestCase(HandlersTestCase):
    """Submission API endpoint class test cases."""

    async def test_post_get_delete_submission(self):
        """Test that submission post and get works."""

        # Test valid submission.

        name = f"name_{uuid.uuid4()}"
        description = f"description_{uuid.uuid4()}"
        project_id = f"project_{uuid.uuid4()}"
        workflow = "SDSX"

        # Post submission.

        submission_id = await self.post_submission(
            name=name, description=description, project_id=project_id, workflow=workflow
        )

        # Get submission.

        submission = await self.get_submission(submission_id)

        assert submission["name"] == name
        assert submission["description"] == description
        assert submission["projectId"] == project_id
        assert submission["workflow"] == workflow

        # Delete submission.

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):
            response = await self.client.delete(f"{API_PREFIX}/submissions/{submission_id}")
            self.assertEqual(response.status, 204)

        # Get submission.

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):
            response = await self.client.get(f"{API_PREFIX}/submissions/{submission_id}")
            self.assertEqual(response.status, 404)

    async def test_post_submission_fails_with_missing_fields(self):
        """Test that submission creation fails with missing fields."""

        data = {
            "name": f"name_{uuid.uuid4()}",
            "title": f"title_{uuid.uuid4()}",
            "description": f"description_{uuid.uuid4()}",
            "projectId": f"project_{uuid.uuid4()}",
            "workflow": "SDSX",
        }

        async def assert_missing_field(field: str):
            _data = {k: v for k, v in data.items() if k != field}
            with self.patch_verify_authorization:
                response = await self.client.post(f"{API_PREFIX}/submissions", json=_data)
                assert response.status == 400
                result = await response.json()
                assert f"'{field}' is a required property" in result["detail"]

        await assert_missing_field("name")
        await assert_missing_field("description")
        await assert_missing_field("projectId")
        await assert_missing_field("workflow")

    async def test_post_submission_fails_with_empty_body(self):
        """Test that submission creation fails when no data in request."""
        with self.patch_verify_authorization:
            response = await self.client.post(f"{API_PREFIX}/submissions")
            json_resp = await response.json()
            self.assertEqual(response.status, 400)
            self.assertIn("JSON is not correctly formatted", json_resp["detail"])

    async def test_post_submission_fails_with_duplicate_name(self):
        """Test that submission creation fails if the submission name already exists in the project."""
        name = f"name_{uuid.uuid4()}"
        project_id = f"project_{uuid.uuid4()}"

        await self.post_submission(name=name, project_id=project_id)

        data = {
            "name": name,
            "title": f"title_{uuid.uuid4()}",
            "description": f"description_{uuid.uuid4()}",
            "projectId": project_id,
            "workflow": "SDSX",
        }

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):
            response = await self.client.post(f"{API_PREFIX}/submissions", json=data)
            json_resp = await response.json()
            self.assertEqual(response.status, 400)
            self.assertEqual(
                f"Submission with name '{name}' already exists in project {project_id}", json_resp["detail"]
            )

    async def test_get_submissions(self):
        """Test that get submissions works."""

        name_1 = f"name_{uuid.uuid4()}"
        name_2 = f"name_{uuid.uuid4()}"
        project_id = f"project_{uuid.uuid4()}"
        title = f"title_{uuid.uuid4()}"
        description = f"description_{uuid.uuid4()}"
        workflow = "SDSX"

        submission_id_1 = await self.post_submission(
            name=name_1, title=title, description=description, project_id=project_id, workflow=workflow
        )
        submission_id_2 = await self.post_submission(
            name=name_2, title=title, description=description, project_id=project_id, workflow=workflow
        )

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):
            response = await self.client.get(f"{API_PREFIX}/submissions?projectId={project_id}")
            self.assertEqual(response.status, 200)
            result = await response.json()

            def _get_submission(submission_id: str) -> dict[str, Any] | None:
                for submission in result["submissions"]:
                    if submission["submissionId"] == submission_id:
                        return submission

                return None

            assert result["page"] == {
                "page": 1,
                "size": 5,
                "totalPages": 1,
                "totalSubmissions": 2,
            }
            assert len(result["submissions"]) == 2
            assert {
                "dateCreated": _get_submission(submission_id_1)["dateCreated"],
                "title": title,
                "description": description,
                "lastModified": _get_submission(submission_id_1)["lastModified"],
                "name": name_1,
                "projectId": project_id,
                "published": False,
                "submissionId": submission_id_1,
                "text_name": " ".join(re.split("[\\W_]", name_1)),
                "workflow": workflow,
            } in result["submissions"]
            assert {
                "dateCreated": _get_submission(submission_id_2)["dateCreated"],
                "title": title,
                "description": description,
                "lastModified": _get_submission(submission_id_2)["lastModified"],
                "name": name_2,
                "projectId": project_id,
                "published": False,
                "submissionId": submission_id_2,
                "text_name": " ".join(re.split("[\\W_]", name_2)),
                "workflow": workflow,
            } in result["submissions"]

    async def test_get_submissions_by_name(self):
        """Test that get submissions by name works."""

        name_1 = f"name_{uuid.uuid4()}"
        name_2 = f"{uuid.uuid4()}"
        name_3 = f"{uuid.uuid4()} name"
        project_id = f"project_{uuid.uuid4()}"
        description = f"description_{uuid.uuid4()}"
        workflow = "SDSX"

        submission_id_1 = await self.post_submission(
            name=name_1, description=description, project_id=project_id, workflow=workflow
        )
        submission_id_2 = await self.post_submission(
            name=name_2, description=description, project_id=project_id, workflow=workflow
        )
        submission_id_3 = await self.post_submission(
            name=name_3, description=description, project_id=project_id, workflow=workflow
        )

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):
            response = await self.client.get(f"{API_PREFIX}/submissions?projectId={project_id}&name=name")
            self.assertEqual(response.status, 200)
            result = await response.json()
            assert len(result["submissions"]) == 2
            assert submission_id_1 in [r["submissionId"] for r in result["submissions"]]
            assert submission_id_3 in [r["submissionId"] for r in result["submissions"]]

    async def test_get_submissions_by_created(self):
        """Test that get submissions by created date."""

        project_id = f"project_{uuid.uuid4()}"
        submission_id = await self.post_submission(project_id=project_id)

        def today_with_offset(days: int = 0) -> str:
            """
            Returns the current date plus or minus the given number of days
            in the format 'YYYY-MM-DD'.
            """
            target_date = datetime.today() + timedelta(days=days)
            return target_date.strftime("%Y-%m-%d")

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):

            async def get_submissions(created_start, created_end):
                if created_start and created_end:
                    response = await self.client.get(
                        f"{API_PREFIX}/submissions?projectId={project_id}&date_created_start={created_start}&date_created_end={created_end}"
                    )
                elif created_start:
                    response = await self.client.get(
                        f"{API_PREFIX}/submissions?projectId={project_id}&date_created_start={created_start}"
                    )
                elif created_end:
                    response = await self.client.get(
                        f"{API_PREFIX}/submissions?projectId={project_id}&date_created_end={created_end}"
                    )
                else:
                    assert False

                assert response.status == 200
                return await response.json()

            async def assert_included(created_start, created_end):
                result = await get_submissions(created_start, created_end)
                assert len(result["submissions"]) == 1
                assert submission_id in [r["submissionId"] for r in result["submissions"]]

            async def assert_not_included(created_start, created_end):
                result = await get_submissions(created_start, created_end)
                assert len(result["submissions"]) == 0

            await assert_included(today_with_offset(-1), today_with_offset(1))
            await assert_included(today_with_offset(0), today_with_offset(1))
            await assert_included(today_with_offset(-1), today_with_offset(0))
            await assert_included(today_with_offset(0), today_with_offset(0))
            await assert_included(today_with_offset(-1), None)
            await assert_included(today_with_offset(0), None)
            await assert_included(None, today_with_offset(1))
            await assert_included(None, today_with_offset(0))

            await assert_not_included(today_with_offset(-1), today_with_offset(-1))
            await assert_not_included(today_with_offset(1), today_with_offset(1))
            await assert_not_included(today_with_offset(1), None)
            await assert_not_included(None, today_with_offset(-1))

    async def test_get_submissions_by_modified(self):
        """Test that get submissions by modified date."""

        project_id = f"project_{uuid.uuid4()}"
        submission_id = await self.post_submission(project_id=project_id)

        def today_with_offset(days: int = 0) -> str:
            """
            Returns the current date plus or minus the given number of days
            in the format 'YYYY-MM-DD'.
            """
            target_date = datetime.today() + timedelta(days=days)
            return target_date.strftime("%Y-%m-%d")

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):

            async def get_submissions(modified_start, modified_end):
                if modified_start and modified_end:
                    response = await self.client.get(
                        f"{API_PREFIX}/submissions?projectId={project_id}&date_modified_start={modified_start}&date_modified_end={modified_end}"
                    )
                elif modified_start:
                    response = await self.client.get(
                        f"{API_PREFIX}/submissions?projectId={project_id}&date_modified_start={modified_start}"
                    )
                elif modified_end:
                    response = await self.client.get(
                        f"{API_PREFIX}/submissions?projectId={project_id}&date_modified_end={modified_end}"
                    )
                else:
                    assert False

                assert response.status == 200
                return await response.json()

            async def assert_included(modified_start, modified_end):
                result = await get_submissions(modified_start, modified_end)
                assert len(result["submissions"]) == 1
                assert submission_id in [r["submissionId"] for r in result["submissions"]]

            async def assert_not_included(modified_start, modified_end):
                result = await get_submissions(modified_start, modified_end)
                assert len(result["submissions"]) == 0

            await assert_included(today_with_offset(-1), today_with_offset(1))
            await assert_included(today_with_offset(0), today_with_offset(1))
            await assert_included(today_with_offset(-1), today_with_offset(0))
            await assert_included(today_with_offset(0), today_with_offset(0))
            await assert_included(today_with_offset(-1), None)
            await assert_included(today_with_offset(0), None)
            await assert_included(None, today_with_offset(1))
            await assert_included(None, today_with_offset(0))

            await assert_not_included(today_with_offset(-1), today_with_offset(-1))
            await assert_not_included(today_with_offset(1), today_with_offset(1))
            await assert_not_included(today_with_offset(1), None)
            await assert_not_included(None, today_with_offset(-1))

    async def test_get_submissions_with_no_submissions(self):
        """Test that get submissions works without project id."""
        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):
            project_id = f"project_{uuid.uuid4()}"

            response = await self.client.get(f"{API_PREFIX}/submissions?projectId={project_id}")
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

    async def test_get_submissions_fails_with_invalid_parameters(self):
        """Test that get submissions fails with invalid parameters."""
        with (
            self.patch_verify_user_project,
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

    async def test_patch_submission(self):
        """Test that submission patch works with correct keys."""
        name = f"name_{uuid.uuid4()}"
        project_id = f"project_{uuid.uuid4()}"
        description = f"description_{uuid.uuid4()}"
        workflow = "SDSX"

        submission_id = await self.post_submission(
            name=name, description=description, project_id=project_id, workflow=workflow
        )

        # Update name.

        new_name = f"name_{uuid.uuid4()}"
        data = {"name": new_name}
        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):
            response = await self.client.patch(f"{API_PREFIX}/submissions/{submission_id}", json=data)
            self.assertEqual(response.status, 200)

        submission = await self.get_submission(submission_id)
        assert submission["name"] == new_name
        assert submission["description"] == description
        assert submission["projectId"] == project_id
        assert submission["workflow"] == workflow

        # Update description.

        new_description = f"description_{uuid.uuid4()}"
        data = {"description": new_description}
        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):
            response = await self.client.patch(f"{API_PREFIX}/submissions/{submission_id}", json=data)
            self.assertEqual(response.status, 200)

        submission = await self.get_submission(submission_id)
        assert submission["name"] == new_name
        assert submission["description"] == new_description
        assert submission["projectId"] == project_id
        assert submission["workflow"] == workflow

    async def test_patch_doi_info(self):
        """Test changing doi info in the submission."""
        submission_id = await self.post_submission()

        data = ujson.load(open(self.TESTFILES_ROOT / "doi" / "test_doi.json"))

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):
            response = await self.client.patch(f"{API_PREFIX}/submissions/{submission_id}/doi", json=data)
            self.assertEqual(response.status, 200)

        submission = await self.get_submission(submission_id)
        assert data == submission["doiInfo"]

    async def test_patch_linked_folder(self):
        """Test changing linked folder in the submission."""
        submission_id = await self.post_submission()
        folder = f"folder_{uuid.uuid4()}"
        data = {"linkedFolder": folder}

        # Set linked folder for the first time works.
        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):
            response = await self.client.patch(f"{API_PREFIX}/submissions/{submission_id}/folder", json=data)
            self.assertEqual(response.status, 204)

        submission = await self.get_submission(submission_id)
        assert submission["linkedFolder"] == folder

        # Change linked folder fails.
        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):
            response = await self.client.patch(f"{API_PREFIX}/submissions/{submission_id}/folder", json=data)
            self.assertEqual(response.status, 400)
            self.assertIn("already has a linked folder", await response.text())

        submission = await self.get_submission(submission_id)
        assert submission["linkedFolder"] == folder

    async def test_patch_rems(self):
        """Test changing rems in the submission."""
        submission_id = await self.post_submission()

        # Set rems with the correct fields works.

        data = {"workflowId": 1, "organizationId": "CSC", "licenses": [1]}

        with self.patch_verify_user_project, self.patch_verify_authorization, self.patch_verify_rems_workflow_licence:
            response = await self.client.patch(f"{API_PREFIX}/submissions/{submission_id}/rems", json=data)
            self.assertEqual(response.status, 200)

        submission = await self.get_submission(submission_id)
        assert submission["rems"] == data

        # Change rems with the correct fields works.

        data = {"workflowId": 2, "organizationId": "CSC", "licenses": [2]}

        with self.patch_verify_user_project, self.patch_verify_authorization, self.patch_verify_rems_workflow_licence:
            response = await self.client.patch(f"{API_PREFIX}/submissions/{submission_id}/rems", json=data)
            self.assertEqual(response.status, 200)

        submission = await self.get_submission(submission_id)
        assert submission["rems"] == data

        # Change rems with missing fields fails.

        data = {
            "workflowId": 3,
        }

        with self.patch_verify_user_project, self.patch_verify_authorization, self.patch_verify_rems_workflow_licence:
            response = await self.client.patch(f"{API_PREFIX}/submissions/{submission_id}/rems", json=data)
            self.assertEqual(response.status, 400)
            error = response.text()
            self.assertIn("Field required", await response.text())

        # Change rems with invalid types fails.

        data = {"workflowId": "invalid", "organizationId": "CSC", "licenses": [3]}

        with self.patch_verify_user_project, self.patch_verify_authorization, self.patch_verify_rems_workflow_licence:
            response = await self.client.patch(f"{API_PREFIX}/submissions/{submission_id}/rems", json=data)
            self.assertEqual(response.status, 400)
            self.assertIn("Input should be a valid integer", await response.text())


class PublishSubmissionHandlerTestCase(HandlersTestCase):
    """Publishing API endpoint class test cases."""

    @pytest.fixture(autouse=True)
    def _inject_fixtures(
        self,
        submission_repository: SubmissionRepository,
        object_repository: ObjectRepository,
        file_repository: FileRepository,
    ):
        self.submission_repository = submission_repository
        self.object_repository = object_repository
        self.file_repository = file_repository

    async def test_publish_submission_csc(self):
        """Test publishing of CSC submission."""

        user_id = "mock-userid"

        # DOI information.
        doi_info = self.doi_info

        # REMS information.
        rems = Rems(workflow_id=1, organization_id=f"organisation_{str(uuid.uuid4())}", licenses=[1, 2])

        # The submission contains no metadata objects.

        submission_title = f"title_{str(uuid.uuid4())}"
        submission_description = f"description_{str(uuid.uuid4())}"

        # The submission contains one file.
        file_path = f"path_{str(uuid.uuid4())}"
        file_bytes = 1024

        # Mock data.
        metax_url = "https://mock.com/"
        metax_id = f"metax_{str(uuid.uuid4())}"
        doi_part1 = f"doi_{str(uuid.uuid4())}"
        doi_part2 = f"doi_{str(uuid.uuid4())}"
        doi = f"{doi_part1}/{doi_part2}"
        rems_resource_id = 1
        rems_catalogue_id = f"catalogue_{str(uuid.uuid4())}"

        # Create submission and files to allow the submission to be published.

        # Create submission.
        workflow = SubmissionWorkflow.SDS
        workflow_config = get_workflow(workflow.value)
        submission_entity = create_submission_entity(
            workflow=workflow,
            title=submission_title,
            description=submission_description,
            document={SUB_FIELD_DOI: doi_info, SUB_FIELD_REMS: rems.json_dump()},
        )
        submission_id = await self.submission_repository.add_submission(submission_entity)

        # Create file.
        file_entity = FileEntity(submission_id=submission_entity.submission_id, path=file_path, bytes=file_bytes)
        await self.file_repository.add_file(file_entity)

        # Publish submission.
        #

        pid_cls = "metadata_backend.services.pid_ms_handler.PIDServiceHandler"
        datacite_cls = "metadata_backend.services.datacite_service_handler.DataciteServiceHandler"
        metax_cls = "metadata_backend.services.metax_service_handler.MetaxServiceHandler"
        rems_cls = "metadata_backend.services.rems_service_handler.RemsServiceHandler"
        file_provider_cls = "metadata_backend.api.services.file.FileProviderService"

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
            # File provider
            patch(f"{file_provider_cls}.list_files_in_folder", new_callable=AsyncMock) as mock_file_provider,
            # Datacite (csc)
            patch(f"{pid_cls}.create_draft_doi_pid", new_callable=AsyncMock) as mock_pid_create_doi,
            patch(f"{pid_cls}.publish", new_callable=AsyncMock) as mock_pid_publish,
            # Datacite (datacite)
            patch(f"{datacite_cls}.create_draft_doi_datacite", new_callable=AsyncMock) as mock_datacite_create_doi,
            patch(f"{datacite_cls}.publish", new_callable=AsyncMock) as mock_datacite_publish,
            # Metax
            patch.dict(os.environ, {"METAX_DISCOVERY_URL": metax_url}),
            patch(f"{metax_cls}.post_dataset_as_draft", new_callable=AsyncMock) as mock_metax_create,
            patch(f"{metax_cls}.update_dataset_with_doi_info", new_callable=AsyncMock) as mock_metax_update_doi,
            patch(f"{metax_cls}.update_draft_dataset_description", new_callable=AsyncMock) as mock_metax_update_descr,
            patch(f"{metax_cls}.publish_dataset", new_callable=AsyncMock) as mock_metax_publish,
            # REMS
            patch(f"{rems_cls}.create_resource", new_callable=AsyncMock) as mock_rems_create_resource,
            patch(f"{rems_cls}.create_catalogue_item", new_callable=AsyncMock) as mock_rems_create_catalogue_item,
        ):
            # Mock file provider.
            mock_file_provider.return_value = FileProviderService.Files(
                [FileProviderService.File(path=file_path, bytes=file_bytes)]
            )
            # Mock Datacite.
            mock_pid_create_doi.return_value = doi
            mock_datacite_create_doi.return_value = doi
            # Mock Metax.
            mock_metax_create.return_value = metax_id
            # Mock Rems.
            mock_rems_create_resource.return_value = rems_resource_id
            mock_rems_create_catalogue_item.return_value = rems_catalogue_id

            # Publish submission.
            response = await self.client.patch(f"{API_PREFIX}/publish/{submission_entity.submission_id}")
            data = await response.json()
            assert response.status == 200
            assert data == {"submissionId": submission_id}

            # Assert Datacite.

            datacite_data = {
                "id": doi,
                "type": "dois",
                "data": {
                    "attributes": {
                        "publisher": "CSC - IT Center for Science",
                        "publicationYear": datetime.now().year,
                        "event": "publish",
                        "schemaVersion": "https://schema.datacite.org/meta/kernel-4",
                        "doi": doi,
                        "prefix": doi_part1,
                        "suffix": doi_part2,
                        "types": {
                            "ris": "DATA",
                            "bibtex": "misc",
                            "citeproc": "dataset",
                            "schemaOrg": "Dataset",
                            "resourceTypeGeneral": "Dataset",
                        },
                        "url": f"{metax_url}{metax_id}",
                        "identifiers": [{"identifierType": "DOI", "doi": doi}],
                        "titles": [{"lang": None, "title": submission_title, "titleType": None}],
                        "descriptions": [
                            {"lang": None, "description": submission_description, "descriptionType": "Other"}
                        ],
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
                        "subjects": [
                            {
                                "subject": "999 - Other",
                                "subjectScheme": "Korkeakoulujen tutkimustiedonkeruussa käytettävä tieteenalaluokitus",
                                "schemeUri": "http://www.yso.fi/onto/okm-tieteenala/conceptscheme",
                                "valueUri": "http://www.yso.fi/onto/okm-tieteenala/ta999",
                                "classificationCode": "999",
                            }
                        ],
                    }
                },
            }

            if workflow_config.publish_config.datacite_config.service == "csc":
                mock_pid_create_doi.assert_awaited_once_with()
                mock_pid_publish.assert_awaited_once_with(datacite_data)
            else:
                mock_datacite_create_doi.assert_awaited_once_with("submission")
                mock_datacite_publish.assert_awaited_once_with(datacite_data)

            # Assert Metax.
            mock_metax_create.assert_awaited_once_with(user_id, doi, submission_title, submission_description)
            mock_metax_update_doi.assert_awaited_once_with(
                {
                    # Remove keywords.
                    **{k: v for k, v in doi_info.items() if k != "keywords"},
                    # Update subjects.
                    "subjects": [
                        {
                            **s,
                            "subjectScheme": "Korkeakoulujen tutkimustiedonkeruussa käytettävä tieteenalaluokitus",
                            "schemeUri": "http://www.yso.fi/onto/okm-tieteenala/conceptscheme",
                            "valueUri": f"http://www.yso.fi/onto/okm-tieteenala/ta{s['subject'].split(' - ')[0]}",
                            "classificationCode": s["subject"].split(" - ")[0],
                        }
                        for s in doi_info.get("subjects", [])
                    ],
                },
                metax_id,
                file_bytes,
                related_dataset=None,
                related_study=None,
            )
            mock_metax_update_descr.assert_awaited_once_with(
                metax_id,
                f"{submission_description}\n\nSD Apply's Application link: {RemsServiceHandler.application_url(rems_catalogue_id)}",
            )

            mock_metax_publish.assert_awaited_once_with(metax_id, doi)

            # Assert Rems.
            mock_rems_create_resource.assert_awaited_once_with(
                doi=doi, organization_id=rems.organization_id, licenses=rems.licenses
            )
            mock_rems_create_catalogue_item.assert_awaited_once_with(
                resource_id=rems_resource_id,
                workflow_id=rems.workflow_id,
                organization_id=rems.organization_id,
                localizations={"en": {"title": submission_title, "infourl": f"{metax_url}{metax_id}"}},
            )

    async def test_publish_submission_fega(self):
        """Test publishing of FEGA submission."""

        user_id = "mock-userid"

        # DOI information.
        doi_info = self.doi_info

        # RENS information.
        rems = Rems(workflow_id=1, organization_id=f"organisation_{str(uuid.uuid4())}", licenses=[1, 2])

        # The submission contains one dataset metadata object.
        dataset_schema = "dataset"
        dataset_title = f"title_{str(uuid.uuid4())}"
        dataset_description = f"description_{str(uuid.uuid4())}"

        # The submission contains one study metadata object.
        study_schema = "study"
        study_title = f"title_{str(uuid.uuid4())}"
        study_description = f"description_{str(uuid.uuid4())}"

        # The submission contains one file.
        file_path = f"path_{str(uuid.uuid4())}"
        file_bytes = 1024

        # Mock data.
        metax_url = "https://mock.com/"
        metax_id = f"metax_{str(uuid.uuid4())}"
        doi_part1 = f"doi_{str(uuid.uuid4())}"
        doi_part2 = f"doi_{str(uuid.uuid4())}"
        doi = f"{doi_part1}/{doi_part2}"
        rems_resource_id = 1
        rems_catalogue_id = f"catalogue_{str(uuid.uuid4())}"

        # Create submission and files to allow the submission to be published.

        # Create submission.
        workflow = SubmissionWorkflow.FEGA
        workflow_config = get_workflow(workflow.value)
        submission_entity = create_submission_entity(
            workflow=workflow, document={SUB_FIELD_DOI: doi_info, SUB_FIELD_REMS: rems.json_dump()}
        )
        submission_id = await self.submission_repository.add_submission(submission_entity)

        # Create metadata objects.

        # Dataset.
        dataset_entity = create_object_entity(
            submission_id=submission_entity.submission_id,
            schema=dataset_schema,
            document={"title": dataset_title, "description": dataset_description},
        )
        await self.object_repository.add_object(dataset_entity)

        # DAC.
        dac_entity = create_object_entity(submission_id=submission_entity.submission_id, schema="dac", document={})
        await self.object_repository.add_object(dac_entity)

        # Policy.
        policy_entity = create_object_entity(
            submission_id=submission_entity.submission_id, schema="policy", document={}
        )
        await self.object_repository.add_object(policy_entity)

        # Study.
        study_entity = create_object_entity(
            submission_id=submission_entity.submission_id,
            schema=study_schema,
            document={"descriptor": {"studyTitle": study_title, "studyAbstract": study_description}},
        )
        await self.object_repository.add_object(study_entity)

        # Create file.
        file_entity = FileEntity(
            submission_id=submission_entity.submission_id,
            object_id=dataset_entity.object_id,
            path=file_path,
            bytes=file_bytes,
        )
        await self.file_repository.add_file(file_entity)

        # Publish submission.
        #

        pid_cls = "metadata_backend.services.pid_ms_handler.PIDServiceHandler"
        datacite_cls = "metadata_backend.services.datacite_service_handler.DataciteServiceHandler"
        metax_cls = "metadata_backend.services.metax_service_handler.MetaxServiceHandler"
        rems_cls = "metadata_backend.services.rems_service_handler.RemsServiceHandler"

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
            # Datacite (csc)
            patch(f"{pid_cls}.create_draft_doi_pid", new_callable=AsyncMock) as mock_pid_create_doi,
            patch(f"{pid_cls}.publish", new_callable=AsyncMock) as mock_pid_publish,
            # Datacite (datacite)
            patch(f"{datacite_cls}.create_draft_doi_datacite", new_callable=AsyncMock) as mock_datacite_create_doi,
            patch(f"{datacite_cls}.publish", new_callable=AsyncMock) as mock_datacite_publish,
            # Metax
            patch.dict(os.environ, {"METAX_DISCOVERY_URL": metax_url}),
            patch(f"{metax_cls}.post_dataset_as_draft", new_callable=AsyncMock) as mock_metax_create,
            patch(f"{metax_cls}.update_dataset_with_doi_info", new_callable=AsyncMock) as mock_metax_update_doi,
            patch(f"{metax_cls}.update_draft_dataset_description", new_callable=AsyncMock) as mock_metax_update_descr,
            patch(f"{metax_cls}.publish_dataset", new_callable=AsyncMock) as mock_metax_publish,
            # REMS
            patch(f"{rems_cls}.create_resource", new_callable=AsyncMock) as mock_rems_create_resource,
            patch(f"{rems_cls}.create_catalogue_item", new_callable=AsyncMock) as mock_rems_create_catalogue_item,
        ):
            # Mock Datacite.
            mock_pid_create_doi.return_value = doi
            mock_datacite_create_doi.return_value = doi
            # Mock Metax.
            mock_metax_create.return_value = metax_id
            # Mock Rems.
            mock_rems_create_resource.return_value = rems_resource_id
            mock_rems_create_catalogue_item.return_value = rems_catalogue_id

            # Publish submission.
            response = await self.client.patch(f"{API_PREFIX}/publish/{submission_entity.submission_id}")
            data = await response.json()
            assert response.status == 200
            assert data == {"submissionId": submission_id}

            # Assert Datacite.

            dataset_datacite_data = {
                "id": doi,
                "type": "dois",
                "data": {
                    "attributes": {
                        "publisher": "CSC - IT Center for Science",
                        "publicationYear": datetime.now().year,
                        "event": "publish",
                        "schemaVersion": "https://schema.datacite.org/meta/kernel-4",
                        "doi": doi,
                        "prefix": doi_part1,
                        "suffix": doi_part2,
                        "types": {
                            "ris": "DATA",
                            "bibtex": "misc",
                            "citeproc": "dataset",
                            "schemaOrg": "Dataset",
                            "resourceTypeGeneral": "Dataset",
                        },
                        "url": f"{metax_url}{metax_id}",
                        "identifiers": [{"identifierType": "DOI", "doi": doi}],
                        "titles": [{"lang": None, "title": dataset_title, "titleType": None}],
                        "descriptions": [
                            {"lang": None, "description": dataset_description, "descriptionType": "Other"}
                        ],
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
                        "subjects": [
                            {
                                "subject": "999 - Other",
                                "subjectScheme": "Korkeakoulujen tutkimustiedonkeruussa käytettävä tieteenalaluokitus",
                                "schemeUri": "http://www.yso.fi/onto/okm-tieteenala/conceptscheme",
                                "valueUri": "http://www.yso.fi/onto/okm-tieteenala/ta999",
                                "classificationCode": "999",
                            }
                        ],
                        "relatedIdentifiers": [
                            {
                                "relationType": "IsDescribedBy",
                                "relatedIdentifier": doi,
                                "resourceTypeGeneral": "Collection",
                                "relatedIdentifierType": "DOI",
                            }
                        ],
                    }
                },
            }

            study_datacite_data = {
                "id": doi,
                "type": "dois",
                "data": {
                    "attributes": {
                        "publisher": "CSC - IT Center for Science",
                        "publicationYear": datetime.now().year,
                        "event": "publish",
                        "schemaVersion": "https://schema.datacite.org/meta/kernel-4",
                        "doi": doi,
                        "prefix": doi_part1,
                        "suffix": doi_part2,
                        "types": {
                            "bibtex": "misc",
                            "citeproc": "collection",
                            "schemaOrg": "Collection",
                            "resourceTypeGeneral": "Collection",
                        },
                        "url": f"{metax_url}{metax_id}",
                        "identifiers": [{"identifierType": "DOI", "doi": doi}],
                        "titles": [{"lang": None, "title": study_title, "titleType": None}],
                        "descriptions": [{"lang": None, "description": study_description, "descriptionType": "Other"}],
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
                        "subjects": [
                            {
                                "subject": "999 - Other",
                                "subjectScheme": "Korkeakoulujen tutkimustiedonkeruussa käytettävä tieteenalaluokitus",
                                "schemeUri": "http://www.yso.fi/onto/okm-tieteenala/conceptscheme",
                                "valueUri": "http://www.yso.fi/onto/okm-tieteenala/ta999",
                                "classificationCode": "999",
                            }
                        ],
                        "relatedIdentifiers": [
                            {
                                "relationType": "Describes",
                                "relatedIdentifier": doi,
                                "resourceTypeGeneral": "Dataset",
                                "relatedIdentifierType": "DOI",
                            }
                        ],
                    }
                },
            }

            if workflow_config.publish_config.datacite_config.service == "csc":
                assert mock_pid_create_doi.await_count == 2
                assert mock_pid_publish.await_count == 2
                assert call(dataset_datacite_data) in mock_pid_publish.await_args_list
                assert call(study_datacite_data) in mock_pid_publish.await_args_list
            else:
                assert mock_datacite_create_doi.await_count == 2
                assert call(dataset_schema) in mock_datacite_create_doi.await_args_list
                assert call(study_schema) in mock_datacite_create_doi.await_args_list
                assert mock_pid_publish.await_count == 2
                assert call(dataset_datacite_data) in mock_datacite_publish.await_args_list
                assert call(study_datacite_data) in mock_datacite_publish.await_args_list

            # Assert Metax.
            assert mock_metax_create.await_count == 2
            assert call(user_id, doi, dataset_title, dataset_description) in mock_metax_create.await_args_list
            assert call(user_id, doi, study_title, study_description) in mock_metax_create.await_args_list
            assert mock_metax_update_doi.await_count == 2
            # Dataset.
            assert (
                call(
                    {
                        # Remove keywords.
                        **{k: v for k, v in doi_info.items() if k != "keywords"},
                        # Update subjects.
                        "subjects": [
                            {
                                **s,
                                "subjectScheme": "Korkeakoulujen tutkimustiedonkeruussa käytettävä tieteenalaluokitus",
                                "schemeUri": "http://www.yso.fi/onto/okm-tieteenala/conceptscheme",
                                "valueUri": f"http://www.yso.fi/onto/okm-tieteenala/ta{s['subject'].split(' - ')[0]}",
                                "classificationCode": s["subject"].split(" - ")[0],
                            }
                            for s in doi_info.get("subjects", [])
                        ],
                    },
                    metax_id,
                    file_bytes,
                    related_dataset=None,
                    related_study=Registration(
                        submission_id=submission_id,
                        object_id=study_entity.object_id,
                        schema_type=study_schema,
                        title=study_title,
                        description=study_description,
                        doi=doi,
                        metax_id=metax_id,
                    ),
                )
                in mock_metax_update_doi.await_args_list
            )
            # Study.
            assert (
                call(
                    {
                        # Remove keywords.
                        **{k: v for k, v in doi_info.items() if k != "keywords"},
                        # Update subjects.
                        "subjects": [
                            {
                                **s,
                                "subjectScheme": "Korkeakoulujen tutkimustiedonkeruussa käytettävä tieteenalaluokitus",
                                "schemeUri": "http://www.yso.fi/onto/okm-tieteenala/conceptscheme",
                                "valueUri": f"http://www.yso.fi/onto/okm-tieteenala/ta{s['subject'].split(' - ')[0]}",
                                "classificationCode": s["subject"].split(" - ")[0],
                            }
                            for s in doi_info.get("subjects", [])
                        ],
                    },
                    metax_id,
                    file_bytes,
                    related_dataset=Registration(
                        submission_id=submission_id,
                        object_id=dataset_entity.object_id,
                        schema_type=dataset_schema,
                        title=dataset_title,
                        description=dataset_description,
                        doi=doi,
                        metax_id=metax_id,
                        rems_url=f"http://mockrems:8003/application?items={rems_catalogue_id}",
                        rems_resource_id=str(rems_resource_id),
                        rems_catalogue_id=rems_catalogue_id,
                    ),
                    related_study=None,
                )
                in mock_metax_update_doi.await_args_list
            )

            mock_metax_update_descr.assert_awaited_once_with(
                metax_id,
                f"{dataset_description}\n\nSD Apply's Application link: {RemsServiceHandler.application_url(rems_catalogue_id)}",
            )

            assert mock_metax_publish.await_count == 2
            assert call(metax_id, doi) in mock_metax_publish.await_args_list

            # Assert Rems.
            mock_rems_create_resource.assert_awaited_once_with(
                doi=doi, organization_id=rems.organization_id, licenses=rems.licenses
            )
            mock_rems_create_catalogue_item.assert_awaited_once_with(
                resource_id=rems_resource_id,
                workflow_id=rems.workflow_id,
                organization_id=rems.organization_id,
                localizations={"en": {"title": dataset_title, "infourl": f"{metax_url}{metax_id}"}},
            )

    async def test_publish_submission_bp(self):
        """Test publishing of BP submission."""

        # DOI information.
        doi_info = self.doi_info

        # RENS information.
        rems = Rems(workflow_id=1, organization_id=f"organisation_{str(uuid.uuid4())}", licenses=[1, 2])

        # The submission contains one dataset metadata object.
        dataset_schema = "bpdataset"
        dataset_title = f"title_{str(uuid.uuid4())}"
        dataset_description = f"description_{str(uuid.uuid4())}"

        # The submission contains one file.
        file_path = f"path_{str(uuid.uuid4())}"
        file_bytes = 1024

        # Mock data.
        beacon_url = "https://mock.com/"
        doi_part1 = f"doi_{str(uuid.uuid4())}"
        doi_part2 = f"doi_{str(uuid.uuid4())}"
        doi = f"{doi_part1}/{doi_part2}"
        rems_resource_id = 1
        rems_catalogue_id = f"catalogue_{str(uuid.uuid4())}"

        # Create submission and files to allow the submission to be published.

        # Create submission.
        workflow = SubmissionWorkflow.BP
        workflow_config = get_workflow(workflow.value)
        submission_entity = create_submission_entity(
            workflow=workflow, document={SUB_FIELD_DOI: doi_info, SUB_FIELD_REMS: rems.json_dump()}
        )
        submission_id = await self.submission_repository.add_submission(submission_entity)

        # Create metadata object.
        object_entity = create_object_entity(
            submission_id=submission_entity.submission_id,
            schema=dataset_schema,
            document={"title": dataset_title, "description": dataset_description},
        )
        await self.object_repository.add_object(object_entity)

        # Create file.
        file_entity = FileEntity(
            submission_id=submission_entity.submission_id,
            object_id=object_entity.object_id,
            path=file_path,
            bytes=file_bytes,
        )
        await self.file_repository.add_file(file_entity)

        # Publish submission.
        #

        pid_cls = "metadata_backend.services.pid_ms_handler.PIDServiceHandler"
        datacite_cls = "metadata_backend.services.datacite_service_handler.DataciteServiceHandler"
        rems_cls = "metadata_backend.services.rems_service_handler.RemsServiceHandler"

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
            # Datacite (csc)
            patch(f"{pid_cls}.create_draft_doi_pid", new_callable=AsyncMock) as mock_pid_create_doi,
            patch(f"{pid_cls}.publish", new_callable=AsyncMock) as mock_pid_publish,
            # Datacite (datacite)
            patch(f"{datacite_cls}.create_draft_doi_datacite", new_callable=AsyncMock) as mock_datacite_create_doi,
            patch(f"{datacite_cls}.publish", new_callable=AsyncMock) as mock_datacite_publish,
            # Metax
            patch.dict(os.environ, {"BEACON_DISCOVERY_URL": beacon_url}),
            # REMS
            patch(f"{rems_cls}.create_resource", new_callable=AsyncMock) as mock_rems_create_resource,
            patch(f"{rems_cls}.create_catalogue_item", new_callable=AsyncMock) as mock_rems_create_catalogue_item,
        ):
            # Mock Datacite.
            mock_pid_create_doi.return_value = doi
            mock_datacite_create_doi.return_value = doi
            # Mock Rems.
            mock_rems_create_resource.return_value = rems_resource_id
            mock_rems_create_catalogue_item.return_value = rems_catalogue_id

            # Publish submission.
            response = await self.client.patch(f"{API_PREFIX}/publish/{submission_entity.submission_id}")
            data = await response.json()
            assert response.status == 200
            assert data == {"submissionId": submission_id}

            # Assert Datacite.

            datacite_data = {
                "id": doi,
                "type": "dois",
                "data": {
                    "attributes": {
                        "publisher": "CSC - IT Center for Science",
                        "publicationYear": datetime.now().year,
                        "event": "publish",
                        "schemaVersion": "https://schema.datacite.org/meta/kernel-4",
                        "doi": doi,
                        "prefix": doi_part1,
                        "suffix": doi_part2,
                        "types": {
                            "ris": "DATA",
                            "bibtex": "misc",
                            "citeproc": "dataset",
                            "schemaOrg": "Dataset",
                            "resourceTypeGeneral": "Dataset",
                        },
                        "url": f"{beacon_url}{doi}",
                        "identifiers": [{"identifierType": "DOI", "doi": doi}],
                        "titles": [{"lang": None, "title": dataset_title, "titleType": None}],
                        "descriptions": [
                            {"lang": None, "description": dataset_description, "descriptionType": "Other"}
                        ],
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
                        "subjects": [
                            {
                                "subject": "999 - Other",
                                "subjectScheme": "Korkeakoulujen tutkimustiedonkeruussa käytettävä tieteenalaluokitus",
                                "schemeUri": "http://www.yso.fi/onto/okm-tieteenala/conceptscheme",
                                "valueUri": "http://www.yso.fi/onto/okm-tieteenala/ta999",
                                "classificationCode": "999",
                            }
                        ],
                    }
                },
            }

            if workflow_config.publish_config.datacite_config.service == "csc":
                mock_pid_create_doi.assert_awaited_once_with()
                mock_pid_publish.assert_awaited_once_with(datacite_data)
            else:
                mock_datacite_create_doi.assert_awaited_once_with(dataset_schema)
                mock_datacite_publish.assert_awaited_once_with(datacite_data)

            # Assert Beacon.
            # TODO(improve): BP beacon service not implement

            # Assert Rems.
            mock_rems_create_resource.assert_awaited_once_with(
                doi=doi, organization_id=rems.organization_id, licenses=rems.licenses
            )
            mock_rems_create_catalogue_item.assert_awaited_once_with(
                resource_id=rems_resource_id,
                workflow_id=rems.workflow_id,
                organization_id=rems.organization_id,
                localizations={"en": {"title": dataset_title, "infourl": f"{beacon_url}{doi}"}},
            )


class ApiKeyHandlerTestCase(HandlersTestCase):
    """API key handler test cases."""

    async def test_post_get_delete_api_key(self) -> None:
        """Test API key creation, listing and revoking."""
        async with transaction(_session_factory, requires_new=True, rollback_new=True):
            with (
                self.patch_verify_authorization,
                self.patch_verify_user_project,
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
                assert key_id_1 in [ApiKey(**key).key_id for key in json]

                # Create second key.
                response = await self.client.post(
                    f"{API_PREFIX}/api/keys", json=ApiKey(key_id=key_id_2).model_dump(mode="json")
                )
                self.assertEqual(response.status, 200)

                # Check first and second key exist.
                response = await self.client.get(f"{API_PREFIX}/api/keys")
                self.assertEqual(response.status, 200)
                json = await response.json()
                assert key_id_1 in [ApiKey(**key).key_id for key in json]
                assert key_id_2 in [ApiKey(**key).key_id for key in json]

                # Remove second key.
                response = await self.client.delete(
                    f"{API_PREFIX}/api/keys", json=ApiKey(key_id=key_id_2).model_dump(mode="json")
                )
                self.assertEqual(response.status, 204)

                # Check first key exists.
                response = await self.client.get(f"{API_PREFIX}/api/keys")
                self.assertEqual(response.status, 200)
                json = await response.json()
                assert key_id_1 in [ApiKey(**key).key_id for key in json]
                assert key_id_2 not in [ApiKey(**key).key_id for key in json]


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


class FilesAPIHandlerTestCase(HandlersTestCase):
    """Files API handler test cases."""

    async def test_get_project_folders(self) -> None:
        """Test getting project folders."""

        project_id = "PRJ123"

        with (
            self.patch_verify_authorization,
            self.patch_verify_user_project,
            patch(
                "metadata_backend.api.services.file.FileProviderService.list_folders",
                return_value=["folder1", "folder2"],
            ),
        ):
            response = await self.client.get(f"{API_PREFIX}/projects/{project_id}/folders")
            self.assertEqual(response.status, 200)

            folders = await response.json()
            assert len(folders) == 2
            assert "folder1" and "folder2" in folders

    async def test_get_files_in_folder(self) -> None:
        """Test getting files in a folder."""

        project_id = "PRJ123"
        folder_name = "folder1"
        file1 = FileProviderService.File(path="S3://folder1/file1.txt", bytes=100)
        file2 = FileProviderService.File(path="S3://folder1/file2.txt", bytes=101)

        with (
            self.patch_verify_authorization,
            self.patch_verify_user_project,
            patch(
                "metadata_backend.api.services.file.FileProviderService.list_files_in_folder",
                return_value=FileProviderService.Files([file1, file2]),
            ),
        ):
            response = await self.client.get(f"{API_PREFIX}/projects/{project_id}/folders/{folder_name}/files")
            self.assertEqual(response.status, 200)

            files = await response.json()
            assert len(files) == 2
            assert files[1]["path"] == "S3://folder1/file2.txt"
            assert files[1]["bytes"] == 101
