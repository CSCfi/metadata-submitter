"""Test API endpoints for user handler methods."""

import json
import os
from unittest.mock import MagicMock, patch

from starlette import status

from metadata_backend.api.models.models import Project, User
from metadata_backend.api.services.project import CscProjectService
from metadata_backend.conf.conf import API_PREFIX
from tests.unit.patches.user import MOCK_PROJECT_ID, MOCK_USER_ID, MOCK_USER_NAME, patch_verify_authorization


async def test_get_user_csc(csc_client) -> None:
    mock_connection = MagicMock()
    mock_connection.__enter__.return_value = mock_connection  # context manager support
    mock_connection.__exit__.return_value = None
    mock_entry = MagicMock()
    mock_entry.entry_to_json.return_value = json.dumps(
        {"dn": "ou=SP_SD-SUBMIT,ou=idm,dc=csc,dc=fi", "attributes": {"CSCPrjNum": [MOCK_PROJECT_ID]}}
    )
    mock_connection.entries = [mock_entry]

    with (
        patch_verify_authorization,
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
        response = csc_client.get(f"{API_PREFIX}/users")
        assert response.status_code == status.HTTP_200_OK

        user = User(**response.json())
        assert user.user_id == MOCK_USER_ID
        assert user.user_name == MOCK_USER_NAME
        assert user.projects == [Project(project_id=MOCK_PROJECT_ID)]


async def test_get_user_nbis(nbis_client) -> None:
    with patch_verify_authorization:
        response = nbis_client.get(f"{API_PREFIX}/users")
        assert response.status_code == status.HTTP_200_OK

        user = User(**response.json())
        assert user.user_id == MOCK_USER_ID
        assert user.user_name == MOCK_USER_NAME
        assert user.projects == [Project(project_id=MOCK_USER_ID)]
