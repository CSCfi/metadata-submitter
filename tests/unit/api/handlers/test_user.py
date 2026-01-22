"""Test API endpoints for user handler methods."""

import json
import os
from unittest.mock import MagicMock, patch

from metadata_backend.api.models.models import Project, User
from metadata_backend.api.services.project import CscProjectService
from metadata_backend.conf.conf import API_PREFIX

from .common import HandlersTestCase


class UserAPIHandlerTestCaseCSC(HandlersTestCase):
    """Test user endpoint for CSC deployment."""

    @classmethod
    def setUpClass(cls):
        cls._env_patch = patch.dict(os.environ, {"DEPLOYMENT": "CSC"})
        cls._env_patch.start()
        super().setUpClass()

    async def test_get_user_csc(self) -> None:
        mock_user_id = "mock-userid"
        mock_user_name = "mock-username"
        project_id = "test_project"

        mock_connection = MagicMock()
        mock_connection.__enter__.return_value = mock_connection  # context manager support
        mock_connection.__exit__.return_value = None
        mock_entry = MagicMock()
        mock_entry.entry_to_json.return_value = json.dumps(
            {"dn": "ou=SP_SD-SUBMIT,ou=idm,dc=csc,dc=fi", "attributes": {"CSCPrjNum": [project_id]}}
        )
        mock_connection.entries = [mock_entry]

        with (
            self.patch_verify_authorization,
            patch.dict(
                os.environ,
                {
                    "CSC_LDAP_HOST": "ldap://mockhost",
                    "CSC_LDAP_USER": "mocl_ldap_user",
                    "CSC_LDAP_PASSWORD": "mock_ldap_password",
                },
            ),
            patch.object(CscProjectService, "_get_connection", return_value=mock_connection),
        ):
            response = await self.client.get(f"{API_PREFIX}/users")
            self.assertEqual(response.status, 200)

            user = User(**await response.json())
            assert user.user_id == mock_user_id
            assert user.user_name == mock_user_name
            assert user.projects == [Project(project_id=project_id)]


class UserAPIHandlerTestCaseNBIS(HandlersTestCase):
    """Test user endpoint for NBIS deployment."""

    @classmethod
    def setUpClass(cls):
        cls._env_patch = patch.dict(os.environ, {"DEPLOYMENT": "NBIS"})
        cls._env_patch.start()
        super().setUpClass()

    async def test_get_user_nbis(self) -> None:
        mock_user_id = "mock-userid"
        mock_user_name = "mock-username"

        with self.patch_verify_authorization:
            response = await self.client.get(f"{API_PREFIX}/users")
            self.assertEqual(response.status, 200)

            user = User(**await response.json())
            assert user.user_id == mock_user_id
            assert user.user_name == mock_user_name
            assert user.projects == [Project(project_id=mock_user_id)]
