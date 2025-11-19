"""Test API endpoints for user handler methods."""

import json
import os
from unittest.mock import MagicMock, patch

from metadata_backend.api.models.models import Project, User
from metadata_backend.conf.conf import API_PREFIX

from .common import HandlersTestCase


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
