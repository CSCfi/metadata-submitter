"""Integration tests for Keystone service."""

from typing import Any

import pytest

from metadata_backend.api.exceptions import ForbiddenUserException, NotFoundUserException
from tests.integration.conf import mock_keystone_url


async def test_keystone_service(client, monkeypatch, mock_pouta_token):
    """Test keystone service."""
    monkeypatch.setenv("KEYSTONE_ENDPOINT", mock_keystone_url)
    from metadata_backend.services.keystone_service import KeystoneServiceHandler

    service = KeystoneServiceHandler()

    # Project ID in mock keystone image
    project_id = "service"

    # Test get project entry errors
    with pytest.raises(NotFoundUserException) as e:
        await service.get_project_entry("nonexistent", mock_pouta_token)
    assert str(e.value) == "Project 'nonexistent' not found for user in Keystone."

    with pytest.raises(ForbiddenUserException) as e:
        await service.get_project_entry(project_id, "invalid_token")
    assert str(e.value) == "Could not log in using the provided AAI token."

    # Get project entry successfully and verify project entry structure
    project_entry = await service.get_project_entry(project_id, mock_pouta_token)
    assert project_entry.id is not None
    assert project_entry.name is not None
    assert project_entry.endpoint is not None
    assert project_entry.token is not None
    assert project_entry.uid is not None
    assert project_entry.uname is not None

    # Create EC2 credentials
    new_creds = await service.get_ec2_for_project(project_entry)
    assert new_creds.access is not None
    assert new_creds.secret is not None
    all_credentials = await _list_ec2_credentials(service, project_entry)
    access_keys = [cred["access"] for cred in all_credentials]
    assert new_creds.access in access_keys

    # Delete EC2 credentials
    status = await service.delete_ec2_from_project(project_entry, new_creds)
    assert status == 204  # No Content on successful deletion
    all_credentials = await _list_ec2_credentials(service, project_entry)
    access_keys = [cred["access"] for cred in all_credentials]
    assert new_creds.access not in access_keys

    # Session cleanup
    await service.close()


async def _list_ec2_credentials(service, project_entry):
    """List all EC2 credentials for a project.

    :param service: KeystoneServiceHandler instance
    :param project_entry: The project entry containing token and user info
    :returns: List of EC2Credentials objects
    """

    resp: dict[str, Any] = await service._request(
        method="GET",
        url=f"{service.base_url}/v3/users/{project_entry.uid}/credentials/OS-EC2",
        headers={
            "X-Auth-Token": project_entry.token,
        },
    )
    credentials_list = []
    for cred in resp.get("credentials", []):
        credentials_list.append(cred)
    return credentials_list
