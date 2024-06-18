"""Test operations with files."""

import logging

from tests.integration.helpers import find_project_file, get_user_data, post_project_file

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


class TestFiles:
    """Test posting and getting files."""

    async def test_post_project_file(self, client_logged_in):
        """Test file posting endpoint.

        :param client_logged_in: HTTP client in which request call is made
        """
        # Get user data: userId and projects
        user_data = await get_user_data(client_logged_in)
        projectId = user_data["projects"][0]["projectId"]

        # Post file and check its creation succeeded
        file_data = {
            "userId": user_data["userId"],
            "projectId": projectId,
            "files": [
                {
                    "path": "s3:/bucket/files/mock",
                    "name": "mock_file.c4gh",
                    "bytes": 100,
                    "encrypted_checksums": [{"str": "string"}],
                    "unencrypted_checksums": [{"str": "string"}],
                }
            ],
        }

        file_ids = await post_project_file(client_logged_in, file_data)
        LOG.debug(f"Created files: {file_ids}")
        assert len(file_ids) == 1

        # Confirm file exists within project
        file_exists = await find_project_file(client_logged_in, projectId, file_ids[0])
        assert file_exists is True
