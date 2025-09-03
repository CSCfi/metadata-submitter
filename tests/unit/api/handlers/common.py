"""Test API endpoints from handlers module."""

import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

from aiohttp import FormData, web
from aiohttp.test_utils import AioHTTPTestCase, make_mocked_coro
from aiohttp.web import Request

from metadata_backend.api.handlers.restapi import RESTAPIHandler
from metadata_backend.api.services.project import ProjectService
from metadata_backend.conf.conf import API_PREFIX
from metadata_backend.server import init


class HandlersTestCase(AioHTTPTestCase):
    """API endpoint class test cases."""

    TESTFILES_ROOT = Path(__file__).parent.parent.parent.parent / "test_files"
    API_PREFIX = API_PREFIX

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
