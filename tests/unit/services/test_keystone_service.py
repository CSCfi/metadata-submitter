"""Test Pouta Keystone service methods."""

import unittest
from unittest.mock import AsyncMock, patch

from aiohttp import web

from metadata_backend.services.keystone_service import KeystoneService


class KeystoneServiceTestCase(unittest.IsolatedAsyncioTestCase):
    """Pouta Keystone service test cases."""

    def setUp(self):
        """Set class for tests."""
        with patch.dict("os.environ", {"KEYSTONE_ENDPOINT": "http://localhost:5001"}):
            self.keystone_service = KeystoneService()

        self.project = KeystoneService.ProjectEntry(
            id="project_uuid",
            name="1000",
            endpoint="endpoint_url",
            token="scoped_token",
            uid="user_uuid",
            uname="testuser",
        )
        self.credentials = KeystoneService.EC2Credentials(access="access_key", secret="secret_key")

        # Mock OIDC authentication response
        self.mock_oidc_resp = AsyncMock()
        self.mock_oidc_resp.status = 200
        self.mock_oidc_resp.headers = {"X-Subject-Token": "unscoped_token_abc"}

        # Setup context manager for OIDC auth
        self.mock_oidc_cm = AsyncMock()
        self.mock_oidc_cm.__aenter__.return_value = self.mock_oidc_resp
        self.mock_oidc_cm.__aexit__.return_value = None

        self.mock_delete_resp = AsyncMock()
        self.mock_delete_resp.status = 204

        self.mock_delete_cm = AsyncMock()
        self.mock_delete_cm.__aenter__.return_value = self.mock_delete_resp
        self.mock_delete_cm.__aexit__.return_value = None

    async def asyncTearDown(self):
        """Close HTTP client after each test."""
        await self.keystone_service.http_client_close()

    async def test_get_project_entry_success(self):
        """Test successful project token fetch."""
        # Projects list response
        mock_projects_resp = {
            "projects": [
                {"id": self.project.id, "name": f"{self.project.name}"},
            ]
        }

        # Mock the scoped token response
        mock_token_resp = {
            "token": {
                "user": {"id": self.project.uid, "name": self.project.uname},
                "roles": [{"name": "object_store_user"}],
                "catalog": [
                    {
                        "type": "object-store",
                        "endpoints": [
                            {"interface": "public", "url": self.project.endpoint},
                            {"interface": "internal", "url": "http://internal"},
                        ],
                    }
                ],
            }
        }

        with patch.object(self.keystone_service._client, "request") as mock_request:
            # Mock the _request method for projects list
            with patch.object(self.keystone_service, "_request", new_callable=AsyncMock) as mock_internal_request:
                mock_internal_request.return_value = mock_projects_resp

                # Setup context manager for token request
                mock_token_resp_obj = AsyncMock()
                mock_token_resp_obj.status = 201
                mock_token_resp_obj.headers = {"X-Subject-Token": self.project.token}
                mock_token_resp_obj.json = AsyncMock(return_value=mock_token_resp)
                mock_token_cm = AsyncMock()
                mock_token_cm.__aenter__.return_value = mock_token_resp_obj
                mock_token_cm.__aexit__.return_value = None
                mock_request.side_effect = [self.mock_oidc_cm, mock_token_cm]

                result = await self.keystone_service.get_project_entry(self.project.name, "token")
                assert result == self.project

    async def test_get_project_entry_invalid_access_token(self):
        """Test that getting project entry with invalid access token raises HTTPForbidden."""
        invalid_access_token = "invalid_token"
        project_name = "test_project"
        self.mock_oidc_resp.status = 401
        self.mock_oidc_cm.__aenter__.return_value = self.mock_oidc_resp

        with patch.object(self.keystone_service._client, "request") as mock_request:
            mock_request.return_value = self.mock_oidc_cm
            with self.assertRaises(web.HTTPForbidden):
                await self.keystone_service.get_project_entry(project_name, invalid_access_token)

    async def test_get_project_entry_project_not_found(self):
        """Test that getting project entry for non-existent project raises HTTPNotFound."""
        access_token = "valid_access_token"
        project_name = "nonexistent_project"
        mock_projects_resp = {"projects": [{"id": "other_project", "name": "project_other"}]}

        with patch.object(self.keystone_service._client, "request") as mock_request:
            mock_request.return_value = self.mock_oidc_cm
            with patch.object(self.keystone_service, "_request", new_callable=AsyncMock) as mock_internal_request:
                mock_internal_request.return_value = mock_projects_resp
                with self.assertRaises(web.HTTPNotFound):
                    await self.keystone_service.get_project_entry(project_name, access_token)

    async def test_get_ec2_for_project_success(self):
        """Test successful EC2 credentials retrieval."""
        mock_response = {
            "credential": {
                "access": "access_key",
                "secret": "secret_key",
            }
        }

        self.keystone_service._request = AsyncMock(return_value=mock_response)
        result = await self.keystone_service.get_ec2_for_project(self.project)
        assert result == self.credentials
        assert self.keystone_service._request.assert_called_once

    async def test_get_ec2_for_project_missing_fields(self):
        """Test EC2 credentials retrieval with missing fields raises HTTPServerError."""
        self.keystone_service._request = AsyncMock(return_value={})
        with self.assertRaises(web.HTTPServerError):
            await self.keystone_service.get_ec2_for_project(self.project)
            assert self.keystone_service._request.assert_called_once

    async def test_delete_ec2_from_project_success(self):
        """Test successful EC2 credentials deletion."""
        with patch.object(self.keystone_service._client, "request") as mock_request:
            mock_request.return_value = self.mock_delete_cm
            status_code = await self.keystone_service.delete_ec2_from_project(self.project, self.credentials)
            assert status_code == 204
            mock_request.assert_called_once()

    async def test_delete_ec2_from_project_not_found(self):
        """Test EC2 credentials deletion when credentials not found."""
        self.mock_delete_resp.status = 404
        self.mock_delete_cm.__aenter__.return_value = self.mock_delete_resp

        with patch.object(self.keystone_service._client, "request") as mock_request:
            mock_request.return_value = self.mock_delete_cm
            status_code = await self.keystone_service.delete_ec2_from_project(self.project, self.credentials)
            assert status_code == 404
