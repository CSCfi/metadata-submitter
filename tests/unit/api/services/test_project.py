"""Test CSC's LDAP service."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest
from aiohttp import web

from metadata_backend.api.models.models import Project
from metadata_backend.api.services.project import CscProjectService, NbisProjectService


async def test_get_user_projects_csc() -> None:
    """Test get user projects for CSC deployment (LDAP)."""
    service = CscProjectService()

    ldap_host = "ldaps://mockhost"
    ldap_port = 636
    ldap_ssl = True
    ldap_user = "mockuser"
    ldap_password = "mockpassword"
    project_id = "test_project"

    with patch.dict(
        os.environ,
        {"CSC_LDAP_HOST": ldap_host, "CSC_LDAP_USER": ldap_user, "CSC_LDAP_PASSWORD": ldap_password},
    ):
        mock_connection = MagicMock()
        mock_connection.__enter__.return_value = mock_connection  # context manager support
        mock_connection.__exit__.return_value = None
        mock_entry = MagicMock()
        mock_entry.entry_to_json.return_value = json.dumps(
            {"dn": "ou=SP_SD-SUBMIT,ou=idm,dc=csc,dc=fi", "attributes": {"CSCPrjNum": [project_id]}}
        )
        mock_connection.entries = [mock_entry]

        with patch.object(CscProjectService, "_get_connection", return_value=mock_connection) as mock_get_connection:
            assert await service.get_user_projects("test") == [Project(project_id=project_id)]

            mock_get_connection.assert_called_once_with(ldap_host, ldap_port, ldap_user, ldap_password, ldap_ssl)


async def test_verify_user_projects_csc() -> None:
    """Test verify user project for CSC deployment (LDAP)."""
    service = CscProjectService()

    with patch.object(service, "get_user_projects", return_value=[Project(project_id="test_project")]):
        assert await service._verify_user_project("test_user", "test_project")
        await service.verify_user_project("test_user", "test_project")

        assert not await service._verify_user_project("test_user", "invalid_project")
        with pytest.raises(web.HTTPUnauthorized):
            await service.verify_user_project("test_user", "-1")


async def test_get_user_projects_nbis() -> None:
    """Test get user projects for NBIS deployment."""
    service = NbisProjectService()

    assert await service.get_user_projects("test_user1") == [Project(project_id="test_user1")]
    assert await service.get_user_projects("test_user2") == [Project(project_id="test_user2")]


async def test_verify_user_projects_nbis() -> None:
    """Test verify user project for NBIS deployment."""
    service = NbisProjectService()

    assert await service._verify_user_project("test_user1", "test_user1")
    await service.verify_user_project("test_user2", "test_user2")

    assert not await service._verify_user_project("test_user1", "test_user2")
    with pytest.raises(web.HTTPUnauthorized):
        await service.verify_user_project("test_user1", "test_user2")
