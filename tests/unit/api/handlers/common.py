"""Test API endpoints from handlers module."""

import uuid
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, make_mocked_coro
from aiohttp.web import Request

from metadata_backend.api.handlers.restapi import RESTAPIHandler
from metadata_backend.api.models.models import Project
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

        self.project_id = "1001"

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

        # Mock get projects.
        self.patch_get_user_projects = patch.object(
            ProjectService, "get_user_projects", new=AsyncMock(return_value=[Project(project_id=self.project_id)])
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

        self.submission_metadata = {
            "publicationYear": date.today().year,
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
        self.user_id = "USR12345678"
        self.test_user = {
            "userId": self.user_id,
            "name": "tester",
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

    async def post_submission(
        self,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        project_id: str | None = None,
        workflow: str = "SD",
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
            submission = {
                "name": name,
                "title": title,
                "description": description,
                "projectId": project_id,
                "workflow": workflow,
            }
            response = await self.client.post(f"{API_PREFIX}/submissions", json=submission)
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
